#!/usr/bin/env python3
"""Read-only APEX input and local pi0.5 inference; action transport exists only in mock."""
import argparse
import asyncio
import json
from functools import partial
import sys
import time
from pathlib import Path

import aiohttp
import cv2
import numpy as np

WORK = Path(__file__).resolve().parents[1] / 'cache/tianji-lora/right-orange-20261117-162906'
HORIZON = 50
ACTION_INDEX = 5
POLICIES = ('base', 'lora3750', 'base1500')
DEFAULT_POLICY = 'lora3750'
PROMPT = 'pick the orange and place it on the black mouse pad'
QUADRANTS = ('tl', 'tr', 'bl', 'br')


def crop(image, quadrant):
    h, w = image.shape[:2]
    y = slice(0, h // 2) if quadrant[0] == 't' else slice(h // 2, h)
    x = slice(0, w // 2) if quadrant[1] == 'l' else slice(w // 2, w)
    return cv2.cvtColor(image[y, x], cv2.COLOR_BGR2RGB)


async def observe(session, base, head, wrist):
    start = time.perf_counter()
    async with session.ws_connect(base + '/ws/state') as ws:
        state = await asyncio.wait_for(ws.receive_json(), timeout=10)
    async with session.get(base + '/stream/quad.mjpg') as response:
        response.raise_for_status()
        reader = aiohttp.MultipartReader.from_response(response)
        part = await reader.next()
        image = cv2.imdecode(np.frombuffer(await part.read(), np.uint8), cv2.IMREAD_COLOR)
    obs = make_observation(state, image, head, wrist)
    print(json.dumps({'read_seconds': time.perf_counter() - start, 'quad_shape': image.shape,
                      'head_shape': obs['head_rgb'].shape, 'wrist_shape': obs['wrist_rgb'].shape,
                      'state_shape': obs['state'].shape}), flush=True)
    return obs


def make_observation(state, image, head, wrist):
    joints = (state.get('joint_states') or {}).get('positions')
    gripper = (state.get('gripper_right') or {}).get('position')
    if joints is None or gripper is None:
        raise ValueError('missing joint_states.positions or gripper_right.position')
    vector = np.asarray(joints[7:14] + [gripper], np.float32)
    if vector.shape != (8,) or not np.isfinite(vector).all() or image is None:
        raise ValueError('invalid state or image')
    obs = dict(head_rgb=crop(image, head), wrist_rgb=crop(image, wrist), state=vector,
               # RightArmInputs requires the actions field even for inference.
               actions=np.zeros((HORIZON, 8), np.float32), prompt=PROMPT)
    return obs


class FakePolicy:
    def infer(self, obs):
        return {'actions': np.tile(obs['state'], (HORIZON, 1))}


def load_policy(fake, num_steps=10, policy=DEFAULT_POLICY):
    started = time.perf_counter()
    policy_name = policy
    checkpoint = None
    if fake:
        policy = FakePolicy()
    else:
        sys.path.insert(0, str(WORK))
        from right_lora import make_config
        from openpi.policies.policy_config import create_trained_policy
        if policy == 'base':
            from dataclasses import replace
            from openpi.models.pi0_config import Pi0Config
            from openpi.training.checkpoints import load_norm_stats
            cfg = replace(make_config('formal'), model=Pi0Config(pi05=True))
            stats = load_norm_stats(cfg.assets_dirs, cfg.data.repo_id)
            checkpoint = Path(__file__).resolve().parents[1] / 'weights/pi05_base'
        elif policy == 'base1500':
            cfg = make_config('base30k-b32')
            checkpoint = cfg.checkpoint_dir / '1500'
            stats = None
        else:
            cfg = make_config('retained')
            checkpoint = cfg.checkpoint_dir / '3750'
            stats = None
        policy = create_trained_policy(cfg, checkpoint, norm_stats=stats, sample_kwargs={'num_steps': num_steps})
    print(json.dumps({'load_seconds': time.perf_counter() - started, 'fake_policy': fake,
                      'policy': policy_name, 'checkpoint': str(checkpoint) if checkpoint else None}), flush=True)
    return policy


async def run(args):
    policy = load_policy(args.fake_policy, args.num_steps, args.policy)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        if args.mock:
            from apex_right_mock import mock_server, send_mock_actions
            async with mock_server(WORK) as base:
                await infer(session, base, policy, "tr", "br", args.iterations,
                            partial(send_mock_actions, session, base))
        else:
            await infer(session, args.url.rstrip("/"), policy, args.head_quadrant, args.wrist_quadrant, args.iterations)


async def infer(session, base, policy, head, wrist, iterations, action_callback=None):
    times = []
    for i in range(iterations):
        obs = await observe(session, base, head, wrist)
        started = time.perf_counter()
        # The model has 32 action dimensions; the right arm uses the first eight.
        result = np.asarray(policy.infer(obs)['actions'], np.float32)[:, :8]
        elapsed = time.perf_counter() - started
        if result.shape != (HORIZON, 8) or not np.isfinite(result).all():
            raise ValueError(f'invalid action shape or nonfinite values: {result.shape}')
        target = result[ACTION_INDEX]
        print(json.dumps({'action_frame': ACTION_INDEX + 1, 'joint_target_rad': target[:7].tolist(),
                          'joint_delta_deg': np.rad2deg(target[:7] - obs['state'][:7]).tolist(),
                          'gripper_prediction': float(target[7])}), flush=True)
        times.append(elapsed)
        print(json.dumps({'iteration': i, 'inference_seconds': elapsed, 'action_shape': result.shape}), flush=True)
        if action_callback is not None:
            await action_callback(result)
    print(json.dumps({'first_inference_seconds': times[0],
                      'steady_mean_seconds': float(np.mean(times[1:])) if len(times) > 1 else None}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--mock', action='store_true')
    mode.add_argument('--url', help='APEX base URL, read-only')
    parser.add_argument('--fake-policy', action='store_true', help='mock mode only')
    parser.add_argument('--head-quadrant', choices=QUADRANTS, help='camera quadrant for --url only')
    parser.add_argument('--wrist-quadrant', choices=QUADRANTS, help='camera quadrant for --url only')
    parser.add_argument('--iterations', type=int, default=3)
    parser.add_argument('--policy', choices=POLICIES, default=DEFAULT_POLICY)
    parser.add_argument('--num-steps', type=int, default=10)
    args = parser.parse_args()
    if args.num_steps <= 0:
        parser.error('--num-steps must be positive')
    if args.iterations < 1 or (args.fake_policy and not args.mock):
        parser.error('iterations must be positive; fake policy requires --mock')
    if args.url and (not args.head_quadrant or not args.wrist_quadrant):
        parser.error('URL mode requires explicit camera quadrants')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
