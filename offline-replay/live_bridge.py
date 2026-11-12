#!/usr/bin/env python3
"""Read-only continuous observations and local pi0.5 inference; never send actions."""
import argparse
import concurrent.futures
import datetime
import io
import json
import math
import queue
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from capture_once import HERE, TASK, camera_stream_class


def read_exact(stream, n):
    data = bytearray()
    while len(data) < n:
        part = stream.read(n - len(data))
        if not part:
            raise EOFError('worker pipe closed')
        data.extend(part)
    return bytes(data)


def recv(stream):
    return read_exact(stream, struct.unpack('!Q', read_exact(stream, 8))[0])


def send(stream, data):
    stream.write(struct.pack('!Q', len(data)) + data)
    stream.flush()


def take_frame(stream):
    before = time.monotonic()
    image, observed = stream.frame()
    return image, {"before_monotonic": before, "observed_monotonic": observed,
                   "after_monotonic": time.monotonic()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--duration', type=float, default=30.0)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'plan_only', 'device_calls': 0, 'task': TASK,
                          'duration_seconds': args.duration, 'requires': '--execute --out NEW_DIRECTORY'}, indent=2))
        return
    if args.out is None or not math.isfinite(args.duration) or args.duration <= 0:
        parser.error('--execute requires --out and a positive finite --duration')
    args.out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'pi05_live_readonly_v1', 'task': TASK, 'duration_seconds': args.duration,
              'timing_semantics': 'host monotonic from each capture request through model response; not sensor exposure time',
              'source_time_synchronized': False, 'gripper_freshness_verified': False,
              'gripper_mapping': 'clip(decoded.q_rad / 1.6, 0, 1); DROID physical equivalence unverified',
              'camera_stopped': {}, 'frames_completed': 0, 'frames_skipped': 0}
    streams, helper, worker = [], None, None
    helper_events = queue.Queue()
    log = (args.out / 'events.jsonl').open('w', buffering=1)
    def event(obj):
        log.write(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n')
    def helper_reader(pipe, diagnostic):
        for line in iter(pipe.readline, ''):
            diagnostic.write(line)
            diagnostic.flush()
            text = line.strip()
            if text == 'PI05_READY':
                helper_events.put(('ready', text))
            else:
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict):
                        helper_events.put(('json', obj))
                except json.JSONDecodeError:
                    pass
        helper_events.put(('eof', None))
    def helper_next(expected, timeout):
        kind, value = helper_events.get(timeout=timeout)
        if kind != expected:
            raise RuntimeError(f'helper expected {expected}, received {kind}: {value}')
        return value
    try:
        worker_err = (args.out / 'worker.stderr').open('w')
        worker = subprocess.Popen([str(HERE.parent / 'envs/openpi-sm87/bin/python'), '-u', str(HERE / 'live_worker.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=worker_err)
        if recv(worker.stdout) != b'READY':
            raise RuntimeError('worker failed to become ready')
        Stream = camera_stream_class()
        for name, channel in (('head_left', 0), ('right_wrist', 3)):
            stream = Stream(channel)
            streams.append((name, stream))
            stream.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(stream.settle) for _, stream in streams]:
                future.result()
            helper_out = (args.out / 'state.stdout').open('w')
            helper_err = (args.out / 'state.stderr').open('w')
            helper = subprocess.Popen([str(HERE / 'capture_state'), '--stream', str(math.ceil(args.duration) + 10)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=helper_err, text=True, bufsize=1)
            reader = threading.Thread(target=helper_reader, args=(helper.stdout, helper_out), daemon=True)
            reader.start()
            helper_next('ready', 30)
            report['sampling_start_monotonic'] = time.monotonic()
            end = report['sampling_start_monotonic'] + args.duration
            while time.monotonic() < end:
                frame_number = report['frames_completed'] + report['frames_skipped']
                started = time.monotonic()
                pending = {name: pool.submit(take_frame, stream) for name, stream in streams}
                helper.stdin.write('\n')
                helper.stdin.flush()
                state = helper_next('json', 10)
                images = {name: future.result() for name, future in pending.items()}
                capture_ready = time.monotonic()
                item = {'frame': frame_number, 'capture_request_monotonic': started,
                        'capture_ready_monotonic': capture_ready,
                        'images': {name: value[1] for name, value in images.items()}, 'state': state}
                if state.get('error') == 'NO_GRIPPER_RESPONSE':
                    item['skipped'] = state['error']
                    event(item)
                    report['frames_skipped'] += 1
                    print(f'frame {frame_number}: gripper feedback timeout; inference skipped', flush=True)
                    continue
                if state.get('error') or not state['joint']['read_returned'] or state['gripper']['response'] is None:
                    raise RuntimeError(f'invalid state: {state}')
                joints = np.asarray(state['joint']['q_rad'], dtype=np.float32)
                q = float(state['gripper']['decoded']['q_rad'])
                if joints.shape != (7,) or not np.isfinite(joints).all() or not math.isfinite(q):
                    raise ValueError('invalid joint or gripper position')
                gripper = np.asarray([np.clip(q / 1.6, 0, 1)], dtype=np.float32)
                observation = io.BytesIO()
                np.savez(observation, exterior=images['head_left'][0], wrist=images['right_wrist'][0],
                         joints=joints, gripper=gripper, prompt=np.asarray(TASK))
                submitted = time.monotonic()
                send(worker.stdin, observation.getvalue())
                with np.load(io.BytesIO(recv(worker.stdout)), allow_pickle=False) as result:
                    received = time.monotonic()
                    actions = result['actions']
                    timing = json.loads(str(result['timing'].item()))
                    if actions.shape != (15, 8) or not np.isfinite(actions).all():
                        raise ValueError(f'invalid action array: {actions.shape}')
                    np.save(args.out / f'actions-{frame_number:06d}.npy', actions)
                item.update(inference_submit_monotonic=submitted, model_response_monotonic=received,
                            end_to_end_seconds=received - started, server_timing=timing,
                            actions_shape=list(actions.shape), actions_finite=True)
                event(item)
                report['frames_completed'] += 1
                print(json.dumps({'frame': item['frame'], 'end_to_end_seconds': item['end_to_end_seconds'],
                                  'server_timing': timing}), flush=True)
            report['sampling_end_monotonic'] = time.monotonic()
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        event({'error': report['error']})
    finally:
        if helper is not None:
            if helper.stdin and not helper.stdin.closed:
                helper.stdin.close()
            try:
                report['state_release'] = helper_next('json', 15)
            except Exception as exc:
                report['state_release_error'] = f'{type(exc).__name__}: {exc}'
            try:
                report['state_helper_returncode'] = helper.wait(timeout=5)
            except subprocess.TimeoutExpired:
                helper.kill()
                report['state_helper_returncode'] = helper.wait()
                report['state_release_error'] = 'helper did not exit; killed'
            reader.join(timeout=2)
            helper_out.close()
            helper_err.close()
        for name, stream in streams:
            try:
                stream.stop()
                report['camera_stopped'][name] = True
            except Exception as exc:
                report['camera_stopped'][name] = str(exc)
        if worker is not None:
            if worker.stdin and not worker.stdin.closed:
                worker.stdin.close()
            try:
                report['worker_returncode'] = worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                report['worker_returncode'] = worker.wait()
            worker_err.close()
        report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        log.close()
    if ('error' in report or report['frames_completed'] == 0 or report.get('state_helper_returncode') != 0 or
            not report.get('state_release', {}).get('release_returned') or
            report.get('worker_returncode') != 0 or any(v is not True for v in report['camera_stopped'].values())):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
