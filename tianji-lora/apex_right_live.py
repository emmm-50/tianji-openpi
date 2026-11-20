#!/usr/bin/env python3
"""Supervised right-arm pi0.5 segments through loopback VLA Host."""
import argparse
import asyncio
import json
import itertools
import math
import sys
import time
from copy import copy
from pathlib import Path

import aiohttp
import cv2
import numpy as np

from apex_right_dry_run import ACTION_INDEX, DEFAULT_POLICY, HORIZON, POLICIES, load_policy, make_observation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'offline-replay'))
from online_retarget import allowed, config, limits

RAD = np.pi / 180


def plan(start, actions, max_joint_delta_deg=None):
    if actions.shape != (HORIZON, 8) or not np.isfinite(actions).all():
        raise ValueError('invalid model output')
    selected = ACTION_INDEX
    target = actions[selected, :7].astype(float)
    a, b = np.rad2deg(start), np.rad2deg(target)
    d = b - a
    max_delta = float(np.max(np.abs(d)))
    if max_joint_delta_deg is not None and max_delta > max_joint_delta_deg:
        raise ValueError(f'max joint displacement {max_delta:.2f}° exceeds limit {max_joint_delta_deg:.2f}°')
    cuts = [0., 1.]
    if d[5] and 0 < -a[5] / d[5] < 1:
        cuts.append(-a[5] / d[5])
    cuts.sort()
    probes = []
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        positive = a[5] + d[5] * (lo + hi) / 2 >= 0
        for coeff in (config[9 if positive else 10], config[12 if positive else 11]):
            poly = np.poly1d(coeff)(np.poly1d([d[5], a[5]])) - np.poly1d([d[6], a[6]])
            for x in np.roots(np.polyder(poly)):
                if abs(x.imag) < 1e-10 and lo < x.real < hi:
                    probes.append(a + x.real * d)
        probes.extend((a + lo * d, a + hi * d))
    if not allowed(np.deg2rad(np.asarray(probes))).all():
        raise ValueError('continuous position or coupling limits exceeded')
    speed = limits[:, 2] * .30
    accel = limits[:, 3]
    duration = max(.02, np.max(1.875 * np.abs(d) / speed),
                   np.max(np.sqrt((10 / np.sqrt(3)) * np.abs(d) / accel)))
    n = math.ceil(duration * 50)
    duration = n / 50
    u = np.arange(n + 1) / n
    blend = u**3 * (10 - 15*u + 6*u*u)
    return start + blend[:, None] * (target - start), selected, duration


class RosWatch:
    def __init__(self, process):
        self.process = process
        self.latest = None
        self.task = asyncio.create_task(self.read())

    async def read(self):
        while line := await self.process.stdout.readline():
            self.latest = json.loads(line)
            feedback = self.latest.pop('joint_feedback', None)
            if feedback:
                print(json.dumps({'timing': 'joint_feedback', 'samples': feedback}), flush=True)

    def state(self):
        if self.process.returncode is not None or self.task.done():
            raise RuntimeError('ROS 只读监视进程已退出或异常')
        if self.latest is None or time.monotonic() - self.latest['monotonic'] > 2:
            raise RuntimeError('ROS 只读监视状态缺失或过期')
        return self.latest

    def route_check(self):
        state = self.state()
        if state['mode'] != 3:
            raise RuntimeError(f"input_mode is {state['mode']!r}, expected 3")
        if not state['mux']:
            raise RuntimeError('joint_cmd_mux is not subscribed to right joint route')

    def robot_ready(self):
        latest = self.state()
        state = latest['robot']
        received = latest['robot_received']
        if received is None or time.monotonic() - received > 2:
            raise RuntimeError('右臂 robot_state 缺失或过期；请在现场确认 Ready/Position')
        if not isinstance(state, list) or len(state) < 2 or state[1] != 1:
            raise RuntimeError(f'右臂 robot_state 未 Ready/Position：{state!r}；请在现场确认 Ready/Position')

    async def wait_initial(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.task.done() or self.process.returncode is not None:
                raise RuntimeError('ROS 只读监视进程已退出或异常')
            if self.latest is not None and self.latest['mode'] is not None and self.latest['robot'] is not None and self.latest['mux']:
                return
            await asyncio.sleep(.1)
        self.route_check()
        self.robot_ready()

    async def close(self):
        if self.process.returncode is None:
            self.process.terminate()
        await self.process.wait()
        await asyncio.gather(self.task, return_exceptions=True)


class ObservationStreams:
    def __init__(self, session, base):
        self.session, self.base = session, base
        self.condition = asyncio.Condition()
        self.samples = {}
        self.open_s = {}
        self.first_s = {}
        self.error = None
        self.tasks = []

    async def __aenter__(self):
        self.started = time.monotonic()
        self.tasks = [asyncio.create_task(self.read_state()), asyncio.create_task(self.read_image())]
        return self

    async def __aexit__(self, *args):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def publish(self, name, value):
        now = time.monotonic()
        async with self.condition:
            previous = self.samples.get(name)
            self.samples[name] = (value, now, now - previous[1] if previous else None)
            if name not in self.first_s:
                self.first_s[name] = now - self.started
            self.condition.notify_all()

    async def failed(self, exc):
        async with self.condition:
            self.error = exc
            self.condition.notify_all()

    async def read_state(self):
        try:
            started = time.monotonic()
            async with self.session.ws_connect(self.base + '/ws/state') as ws:
                self.open_s['state'] = time.monotonic() - started
                while True:
                    await self.publish('state', await ws.receive_json())
        except Exception as exc:
            await self.failed(exc)

    async def read_image(self):
        try:
            started = time.monotonic()
            async with self.session.get(self.base + '/stream/quad.mjpg',
                                        timeout=aiohttp.ClientTimeout(total=None)) as response:
                response.raise_for_status()
                self.open_s['image'] = time.monotonic() - started
                reader = aiohttp.MultipartReader.from_response(response)
                while True:
                    part = await reader.next()
                    if part is None:
                        raise EOFError('MJPEG stream ended')
                    await self.publish('image', await part.read())
        except Exception as exc:
            await self.failed(exc)

    async def fresh(self, names, timeout):
        requested = time.monotonic()
        async with asyncio.timeout(timeout), self.condition:
            await self.condition.wait_for(lambda: self.error is not None or all(
                name in self.samples and self.samples[name][1] >= requested for name in names))
            if self.error is not None:
                raise RuntimeError('observation stream failed') from self.error
            return {name: self.samples[name] for name in names}

    async def snapshot(self):
        samples = await self.fresh(('state',), 3)
        data = samples['state'][0]
        joints = (data.get('joint_states') or {}).get('positions')
        if joints is None:
            raise ValueError('missing joint feedback')
        q = np.asarray(joints[7:14], float)
        if q.shape != (7,) or not np.isfinite(q).all():
            raise ValueError('invalid joint feedback')
        return q

    async def observe(self):
        started = time.monotonic()
        samples = await self.fresh(('state', 'image'), 10)
        received = time.monotonic()
        image = cv2.imdecode(np.frombuffer(samples['image'][0], np.uint8), cv2.IMREAD_COLOR)
        obs = make_observation(samples['state'][0], image, 'tr', 'br')
        done = time.monotonic()
        metrics = {'observe_wait_s': received - started, 'observe_decode_s': done - received,
                   'state_received_monotonic_s': samples['state'][1],
                   'image_received_monotonic_s': samples['image'][1],
                   'state_receive_interval_s': samples['state'][2],
                   'image_receive_interval_s': samples['image'][2],
                   'state_image_receive_gap_s': samples['image'][1] - samples['state'][1]}
        return obs, metrics


async def send_points(action_ws, points, timing=False, trace=False):
    intervals, sends, acks, late = [], [], [], []
    point_times = []
    last_send = None
    first_send = None
    for point in points:
        if last_send is not None:
            now = time.monotonic()
            ready_at = max(last_send + .02, now)
            await asyncio.sleep(ready_at - now)
        previous_send = last_send
        last_send = time.monotonic()
        if timing:
            if first_send is None:
                first_send = last_send
            if previous_send is not None:
                interval = last_send - previous_send
                intervals.append(interval)
                late.append(last_send - ready_at)
        send_wall_us = time.time_ns() // 1000 if trace else None
        await action_ws.send_json({'jointcmd_right': point.tolist()})
        sent = time.monotonic() if timing else None
        ack = await action_ws.receive_json()
        if trace:
            point_times.append([send_wall_us, time.time_ns() // 1000])
        if timing:
            received = time.monotonic()
            sends.append(sent - last_send)
            acks.append(received - sent)
        if not ack.get('success') or ack.get('suppressed'):
            raise RuntimeError(f'action rejected or suppressed: {ack}')
    if timing:
        def stats(values):
            return {'median': float(np.median(values)), 'max': max(values)} if values else None
        summary = {'point_interval_s': stats(intervals), 'send_json_s': stats(sends),
                   'ack_wait_s': stats(acks), 'schedule_late_s': stats(late),
                   'send_span_s': last_send - first_send if first_send is not None else 0.,
                   'send_through_last_ack_s': received - first_send if first_send is not None else 0.,
                   'points': len(sends)}
        if trace:
            summary['point_send_ack_wall_us'] = point_times
        return summary


async def execute(streams, action_ws, policy, segments, gripper, check_route, robot_ready, timing=False, ws_open_s=None, max_joint_delta_deg=None):
    last_gripper = None
    for segment in range(1, segments + 1) if segments else itertools.count(1):
        if segment == 1:
            robot_ready()
            check_route()
            q_hold = await streams.snapshot()
            if not allowed(q_hold[None, :]).all():
                raise RuntimeError('hold position outside joint or coupling limits')
            hold_timing = await send_points(action_ws, np.tile(q_hold, (151, 1)), timing)
            if timing:
                print(json.dumps({'timing': 'hold', 'ws_open_s': ws_open_s, **hold_timing}), flush=True)
        started = time.monotonic() if timing else None
        obs, observation_timing = await streams.observe()
        observed = time.monotonic() if timing else None
        predicted = np.asarray((await asyncio.to_thread(policy.infer, obs))['actions'], float)[:, :8]
        inferred = time.monotonic() if timing else None
        q = await streams.snapshot()
        start_read = time.monotonic() if timing else None
        points, index, duration = plan(q, predicted, max_joint_delta_deg)
        planned = time.monotonic() if timing else None
        print(json.dumps({'segment': segment, 'chosen_frame': index, 'duration_s': duration,
                          'samples': len(points), 'max_displacement_deg': float(np.max(np.abs(points[-1] - q)) / RAD)}), flush=True)
        check_route()
        send_timing = await send_points(action_ws, points, timing, trace=timing)
        wait_started = time.monotonic() if timing else None
        if gripper:
            await asyncio.sleep(.1)
        waited = time.monotonic() if timing else None
        final = await streams.snapshot()
        if timing:
            feedback_read = time.monotonic()
            print(json.dumps({'timing': 'segment', 'segment': segment,
                              'observe_s': observed - started, 'infer_s': inferred - observed,
                              'start_snapshot_s': start_read - inferred, 'plan_s': planned - start_read,
                              'fixed_wait_s': waited - wait_started if gripper else 0.0,
                              'final_snapshot_s': feedback_read - waited,
                              'arm_cycle_s': feedback_read - started,
                              'last_ack_monotonic_s': wait_started,
                              'tracking_target_right_rad': points[-1].tolist(),
                              **({'state_ws_open_s': streams.open_s.get('state'),
                                  'image_http_open_s': streams.open_s.get('image'),
                                  'state_first_receive_s': streams.first_s.get('state'),
                                  'image_first_receive_s': streams.first_s.get('image')} if segment == 1 else {}),
                              **observation_timing, **send_timing}), flush=True)
        target_delta = points[-1] - q
        actual_delta = final - q
        axis = int(np.argmax(np.abs(target_delta)))
        print(json.dumps({'segment': segment, 'target_max_displacement_deg': float(np.max(np.abs(target_delta)) / RAD),
                          'actual_max_displacement_deg': float(np.max(np.abs(actual_delta)) / RAD),
                          'endpoint_max_error_deg': float(np.max(np.abs(final - points[-1])) / RAD),
                          'main_axis': axis + 1, 'main_axis_actual_deg': float(actual_delta[axis] / RAD)}), flush=True)
        if gripper:
            value = float(predicted[index, 7] >= .5)
            if value != last_gripper:
                check_route()
                await action_ws.send_json({'gripper_right': value})
                ack = await action_ws.receive_json()
                if not ack.get('success') or ack.get('suppressed'):
                    raise RuntimeError(f'gripper rejected or suppressed: {ack}')
                last_gripper = value
                print(json.dumps({'gripper_command': value}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--segments', type=int, default=0, help='number of segments; 0 repeats until stopped')
    parser.add_argument('--gripper', action='store_true', help='enable binary model gripper commands after arm segment')
    parser.add_argument('--timing', action='store_true', help='print timing summaries for hold and each segment')
    parser.add_argument('--num-steps', type=int, default=10, help='policy sampling steps (default: 10)')
    parser.add_argument('--policy', choices=POLICIES, default=DEFAULT_POLICY)
    parser.add_argument('--max-joint-delta-deg', type=float, help='reject a segment exceeding this single-axis displacement')
    args = parser.parse_args()
    if args.max_joint_delta_deg is not None and (not math.isfinite(args.max_joint_delta_deg) or args.max_joint_delta_deg <= 0):
        parser.error('--max-joint-delta-deg must be finite and positive')
    if args.segments < 0:
        parser.error('--segments must be nonnegative')
    if args.num_steps <= 0:
        parser.error('--num-steps must be positive')
    print('WARNING: host snapshots lack source timestamps; stopping transmission does not revoke retained targets.', flush=True)
    async def live():
        watcher_path = Path(__file__).with_name('apex_right_ros_watch.py')
        process = await asyncio.create_subprocess_exec(
            'bash', '-c', 'source /etc/apex/apex_ros_env.sh; exec /usr/bin/python3 -u "$@"',
            'ros-watch', str(watcher_path), *(['--timing'] if args.timing else []), stdout=asyncio.subprocess.PIPE)
        watch = RosWatch(process)
        try:
            await watch.wait_initial()
            watch.route_check()
            policy = await asyncio.to_thread(load_policy, False, args.num_steps, args.policy)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                base = 'http://127.0.0.1:8000'
                async with ObservationStreams(session, base) as streams:
                    observation, _ = await streams.observe()
                    warmup_started = time.monotonic()
                    # Share the JIT sampler while keeping the live policy's RNG.
                    await asyncio.to_thread(copy(policy).infer, observation)
                    print(json.dumps({'warmup_seconds': time.monotonic() - warmup_started,
                                      'num_steps': args.num_steps}), flush=True)
                    opened = time.monotonic() if args.timing else None
                    async with session.ws_connect(base + '/ws/action?ack=true') as action_ws:
                        ws_open_s = time.monotonic() - opened if args.timing else None
                        await execute(streams, action_ws, policy, args.segments, args.gripper,
                                      watch.route_check, watch.robot_ready, args.timing, ws_open_s,
                                      args.max_joint_delta_deg)
        finally:
            await watch.close()
    try:
        asyncio.run(live())
    except KeyboardInterrupt:
        print('Interrupted; sending stopped. Retained target may remain active.', flush=True)


if __name__ == '__main__':
    main()
