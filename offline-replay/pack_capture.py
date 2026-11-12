#!/usr/bin/env python3
"""Pack a completed single observation for offline replay; no device access."""
import argparse
import json
from pathlib import Path
import numpy as np


def read_ppm(path):
    # capture_once writes exactly this binary P6 RGB8 header and raster.
    with path.open('rb') as f:
        if f.readline() != b'P6\n':
            raise ValueError(f'{path}: expected P6')
        dimensions = f.readline().split()
        if len(dimensions) != 2 or f.readline() != b'255\n':
            raise ValueError(f'{path}: invalid RGB8 header')
        width, height = map(int, dimensions)
        if width <= 0 or height <= 0:
            raise ValueError(f'{path}: invalid dimensions')
        pixels = f.read()
    if len(pixels) != width * height * 3:
        raise ValueError(f'{path}: incomplete or extra raster data')
    return np.frombuffer(pixels, dtype=np.uint8).reshape(height, width, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path, help='new NPZ file')
    args = parser.parse_args()
    capture = json.loads((args.capture / 'capture.json').read_text())
    state = json.loads((args.capture / 'state.json').read_text())
    if capture.get('error') or capture.get('state_helper_returncode') != 0 or state.get('error'):
        raise ValueError('capture or state helper did not complete successfully')
    if not state['joint']['read_returned'] or state['gripper']['response'] is None:
        raise ValueError('missing joint or gripper response')
    images = []
    for name in ('head_left', 'right_wrist'):
        info = capture['images'][name]
        image = read_ppm(args.capture / info['file'])
        if info['color'] != 'RGB8' or image.shape != (info['height'], info['width'], 3):
            raise ValueError(f'{name}: image metadata mismatch')
        images.append(image)
    joints = np.asarray(state['joint']['q_rad'], dtype=np.float32)
    q = float(state['gripper']['decoded']['q_rad'])
    if joints.shape != (7,) or not np.isfinite(joints).all() or not np.isfinite(q):
        raise ValueError('invalid joint or gripper position')
    raw_ratio = q / 1.6
    gripper = np.asarray([np.clip(raw_ratio, 0, 1)], dtype=np.float32)
    prompt = capture['task']
    if not isinstance(prompt, str) or not prompt:
        raise ValueError('missing task')
    metadata = {'source': 'capture_once', 'capture_directory': str(args.capture.resolve()),
                'capture': capture, 'state': state,
                'image_mapping': {'exterior_rgb': 'head_left', 'wrist_rgb': 'right_wrist'},
                'gripper_mapping': {'meaning': 'configured_motor_position', 'q_rad': q,
                                    'motor_target_range_rad': [0, 1.6], 'raw_ratio': raw_ratio,
                                    'clipped_ratio': float(gripper[0]),
                                    'formula': 'clip(decoded.q_rad / 1.6, 0, 1)',
                                    'physical_opening_or_droid_equivalence_verified': False},
                'synchronization': 'sensor synchronization unverified; timestamps are host observations',
                'gripper_freshness_verified': False}
    # Exclusive creation avoids replacing prior evidence, including if conversion fails.
    with args.output.open('xb') as f:
        try:
            np.savez(f, exterior_rgb=images[0], wrist_rgb=images[1], joint_position=joints,
                     gripper_position=gripper, prompt=np.asarray(prompt),
                     metadata_json=np.asarray(json.dumps(metadata, ensure_ascii=False)))
        except Exception:
            f.close()
            args.output.unlink()
            raise
    print(f'saved {args.output}')


if __name__ == '__main__':
    main()
