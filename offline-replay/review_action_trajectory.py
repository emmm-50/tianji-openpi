#!/usr/bin/env python3
"""Offline hypothetical DROID action interpretation; no device or control calls."""
import argparse
import csv
import importlib.util
import json
import math
import subprocess
from pathlib import Path
import numpy as np
ROOT = Path('/home/nvidia/cph_dev/pi05/offline-replay')
LIVE = ROOT / 'evidence/live-right-20261112_150459_559859520'
REAL = ROOT / 'evidence/real-right-20261112_144023_243023462'
CONFIG = Path('/home/nvidia/wsb_ws/resources/marvin/vendor_sdk/CommonConfig/ccs_m6_40.MvKDCfg')
CONFIG_READER = Path('/home/nvidia/wsb_ws/tools/review_model_compatibility.py')
FK = '/home/nvidia/wsb_ws/build/direct/native/mios_runtime/mios_kinematics_fixture'
DT = 1 / 15

def build_data(live, real):
    events = {e['frame']: e for e in map(json.loads, (live / 'events.jsonl').read_text().splitlines())}
    blocks = []
    for p in sorted(live.glob('actions-*.npy')):
        frame = int(p.stem.split('-')[1])
        e = events[frame]
        blocks.append((f'live-{frame:06}', p, np.array(e['state']['joint']['q_rad'], float)))
    blocks.append(('real', real / 'replay/actions.npy', np.array(json.loads((real / 'state.json').read_text())['joint']['q_rad'], float)))
    samples = []
    entries = []
    data = []
    for name, path, q0 in blocks:
        a = np.load(path, allow_pickle=False)
        assert a.shape == (15, 8) and np.isfinite(a).all() and (q0.shape == (7,)) and np.isfinite(q0).all()
        u = np.clip(a[:, :7], -1, 1)
        qs = np.vstack([q0, q0 + np.cumsum(0.2 * u, axis=0)])
        vel = np.diff(qs, axis=0) / DT
        acc = np.diff(vel, axis=0) / DT
        for step, q in enumerate(qs):
            samples.append({'q_rad': [[0.0] * 7, q.tolist()], 'dq_rad_s': [[0.0] * 7, [0.0] * 7], 'observed_monotonic': 0.0, 'now_monotonic': 0.0, 'source_progress_verified': True, 'joint_feedback_valid': True, 'recorded_input': True})
            entries.append((name, step, q, None if step == 0 else int(a[step - 1, 7] > 0.5)))
        yielddata = {'name': name, 'path': str(path), 'raw_action_min': float(a.min()), 'raw_action_max': float(a.max()), 'q': qs, 'vel': vel, 'acc': acc, 'grip': a[:, 7]}
        data.append(yielddata)
    return (data, samples, entries)

def read_config():
    spec = importlib.util.spec_from_file_location('model_compatibility', CONFIG_READER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.config_rows(CONFIG)[1]
    limits = np.array([row[4:8] for row in rows[1:8]], dtype=float)
    return (limits, np.array(rows[9:13], dtype=float))

def run(live, real, out):
    out.mkdir(parents=True, exist_ok=False)
    data, samples, entries = build_data(live, real)
    limits, boundary = read_config()
    results = []
    meta = None
    for i in range(0, len(samples), 256):
        p = subprocess.run([FK, '--evaluate-stdin'], input=json.dumps(samples[i:i + 256]), text=True, capture_output=True)
        assert p.returncode == 0, p.stderr
        x = json.loads(p.stdout)
        assert x['sdk_calls'] == 0 and (not x['hardware_execute'])
        meta = {k: x[k] for k in ['kinematics_backend', 'sdk_config_sha256', 'model_sha256']}
        results.extend(x['results'])
    assert len(results) == len(entries)
    worst = {}
    counts = {'position_samples': 0, 'coupling_samples': 0, 'velocity_intervals': 0, 'acceleration_intervals': 0}
    block_reports = []

    def update(key, value, name, step, joint, extra=None):
        if key not in worst or value > worst[key]['value']:
            worst[key] = {'value': float(value), 'block': name, 'step': step, 'joint': joint, **(extra or {})}
    rows = []
    offset = 0
    for d in data:
        name = d['name']
        q = d['q']
        deg = np.degrees(q)
        vel = np.degrees(d['vel'])
        acc = np.degrees(d['acc'])
        pos = np.maximum(deg - limits[:, 1], limits[:, 0] - deg)
        j6 = deg[:, 5]
        j7 = deg[:, 6]
        upper_indices = np.where(j6 >= 0, 0, 1)
        lower_indices = np.where(j6 >= 0, 3, 2)
        upper = boundary[upper_indices, 0] * j6 * j6 + boundary[upper_indices, 1] * j6 + boundary[upper_indices, 2]
        lower = boundary[lower_indices, 0] * j6 * j6 + boundary[lower_indices, 1] * j6 + boundary[lower_indices, 2]
        coupled = np.maximum(j7 - upper, lower - j7)
        counts['position_samples'] += int(np.any(pos > 0, axis=1).sum())
        counts['coupling_samples'] += int((coupled > 0).sum())
        counts['velocity_intervals'] += int(np.any(np.abs(vel) > limits[:, 2], axis=1).sum())
        counts['acceleration_intervals'] += int(np.any(np.abs(acc) > limits[:, 3], axis=1).sum())
        for key, arr in [('position_excess_deg', pos), ('velocity_ratio', np.abs(vel) / limits[:, 2]), ('acceleration_ratio', np.abs(acc) / limits[:, 3])]:
            i, j = np.unravel_index(np.argmax(arr), arr.shape)
            update(key, arr[i, j], name, int(i + (2 if key == 'acceleration_ratio' else 1 if key == 'velocity_ratio' else 0)), int(j + 1))
        i = int(np.argmax(coupled))
        update('coupling_excess_deg', coupled[i], name, i, 'J6/J7')
        transforms = [np.array(results[offset + i][1]['O_T_endpoint']) for i in range(16)]
        start = transforms[0]
        end = transforms[-1]
        displacement = end[:3, 3] - start[:3, 3]
        angle = math.acos(float(np.clip((np.trace(start[:3, :3].T @ end[:3, :3]) - 1) / 2, -1, 1)))
        dist = float(np.linalg.norm(displacement))
        update('flange_displacement_m', dist, name, 15, None)
        block_reports.append({'block': name, 'action_file': d['path'], 'raw_action_range': [d['raw_action_min'], d['raw_action_max']], 'flange_end_displacement_m': displacement.tolist(), 'flange_end_distance_m': dist, 'flange_end_rotation_rad': angle, 'position_violation_steps': np.where(np.any(pos > 0, axis=1))[0].tolist(), 'coupling_violation_steps': np.where(coupled > 0)[0].tolist(), 'velocity_violation_steps': (np.where(np.any(np.abs(vel) > limits[:, 2], axis=1))[0] + 1).tolist(), 'acceleration_violation_steps': (np.where(np.any(np.abs(acc) > limits[:, 3], axis=1))[0] + 2).tolist(), 'gripper_open_steps': int(np.sum(d['grip'] <= 0.5)), 'gripper_close_steps': int(np.sum(d['grip'] > 0.5))})
        for step, T in enumerate(transforms):
            rows.append([name, step, *q[step], *deg[step], *T[:3, 3], *T[:3, :3].flatten(), '' if step == 0 else 'close' if d['grip'][step - 1] > 0.5 else 'open'])
        offset += 16
    summary = {'scope': 'Offline hypothetical analysis only; not commands, trajectories for execution, collision, environment, TCP, dynamics or physical validation.', 'assumptions': ['Each block starts independently at its paired saved q_rad; feedback time and axis mapping not verified.', 'First seven action components same-index and same-sign to assumed right joints; clip [-1,1], delta=0.2*u rad per 1/15 s; DROID reference is not verified for Tianji or training deployment.', 'Gripper >0.5 close, otherwise open per DROID; historical right target increasing closes, assumed software range 0..1.6 rad; endpoints do not establish equivalent physical opening.', 'Velocity is interval delta/dt; acceleration is difference between adjacent interval velocities/dt; initial and terminal velocity unknown and excluded. Limits are nominal 100% PNVA, not operational authorization.', 'FK is nominal arm B endpoint/flange; no calibration, TCP or collision verification.', 'The fixture requires source_progress_verified=true and joint_feedback_valid=true to evaluate; these are synthetic interface flags, not evidence of feedback freshness. The unused arm A is zero-filled.'], 'counts': {'blocks': len(data), 'samples': len(entries), **counts}, 'worst': worst, 'model': meta, 'blocks': block_reports}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    representative = {worst[k]['block'] for k in worst} | {'real'}
    with (out / 'representative.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['block', 'step'] + [f'q{i}_rad' for i in range(1, 8)] + [f'q{i}_deg' for i in range(1, 8)] + ['flange_x_m', 'flange_y_m', 'flange_z_m'] + [f'R{i}{j}' for i in range(3) for j in range(3)] + ['gripper_candidate_intent'])
        w.writerows((r for r in rows if r[0] in representative))
    print(json.dumps({'out': str(out), 'counts': summary['counts'], 'worst': worst}, indent=2))
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', type=Path, default=LIVE, help='Saved live evidence directory')
    parser.add_argument('--real', type=Path, default=REAL, help='Saved single-observation evidence directory')
    parser.add_argument('--out', type=Path, required=True, help='New output directory; must not already exist')
    args = parser.parse_args()
    run(args.live, args.real, args.out)
