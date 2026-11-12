#!/usr/bin/env python3
"""Offline single-frame DROID inference; no robot command output."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
os.environ.setdefault("OPENPI_DATA_HOME", str(ROOT / "jax-sm87/cache/openpi"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path[:0] = [str(ROOT / "openpi/src"), str(ROOT / "openpi/packages/openpi-client/src")]
import numpy as np


def load_observation(path):
    with np.load(path, allow_pickle=False) as data:
        exterior, wrist = data["exterior_rgb"], data["wrist_rgb"]
        joints, gripper = data["joint_position"], data["gripper_position"]
        prompt = str(data["prompt"].item())
        metadata = json.loads(str(data["metadata_json"].item()))
    for image in (exterior, wrist):
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[-1] != 3:
            raise ValueError("images must be HWC uint8 RGB")
    if joints.shape != (7,) or gripper.shape != (1,):
        raise ValueError("joint_position and gripper_position must be (7,) and (1,)")
    if not np.isfinite(joints).all() or not np.isfinite(gripper).all():
        raise ValueError("state must be finite")
    return {"observation/exterior_image_1_left": exterior,
            "observation/wrist_image_left": wrist,
            "observation/joint_position": joints,
            "observation/gripper_position": gripper, "prompt": prompt}, metadata


def example_action(actions):
    result = actions.copy()
    result[..., -1] = (result[..., -1] > 0.5).astype(result.dtype)
    return np.clip(result, -1, 1)


def build_policy(num_steps=10):
    checkpoint = ROOT / "weights/pi05_droid"
    import jax.numpy as jnp
    from openpi import transforms
    from openpi.models import model as model_lib
    from openpi.policies import policy
    from openpi.shared import normalize
    from openpi.training import config
    cfg = config.get_config("pi05_droid")
    model = cfg.model.load(model_lib.restore_params(checkpoint / "params", dtype=jnp.bfloat16))
    data = cfg.data.create(cfg.assets_dirs, cfg.model)
    stats = normalize.load(checkpoint / "assets" / data.asset_id)
    agent = policy.Policy(model, transforms=[transforms.InjectDefaultPrompt(None), *data.data_transforms.inputs,
        transforms.Normalize(stats, use_quantiles=data.use_quantile_norm), *data.model_transforms.inputs],
        output_transforms=[*data.model_transforms.outputs,
        transforms.Unnormalize(stats, use_quantiles=data.use_quantile_norm), *data.data_transforms.outputs],
        metadata=cfg.policy_metadata, sample_kwargs={"num_steps": num_steps})
    return agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="new output directory")
    args = parser.parse_args()
    obs, metadata = load_observation(args.input)
    args.output.mkdir(parents=True, exist_ok=False)
    import jax
    num_steps = 10
    checkpoint = ROOT / "weights/pi05_droid"
    cfg_name = "pi05_droid"
    agent = build_policy(num_steps)
    output = agent.infer(obs)
    actions = output["actions"]
    np.save(args.output / "actions.npy", actions)
    np.save(args.output / "droid_example_clipped.npy", example_action(actions))
    (args.output / "metadata.json").write_text(json.dumps({"input": str(args.input.resolve()), "source": metadata,
        "config": cfg_name, "checkpoint": str(checkpoint), "xla_flags": os.environ.get("XLA_FLAGS"),
        "device": [str(d) for d in jax.devices()], "num_steps": num_steps, "droid_example_clipped": "official example threshold and clip only; not a TianJi mapping", "shape": list(actions.shape),
        "dtype": str(actions.dtype), "finite": bool(np.isfinite(actions).all()),
        "policy_timing": output.get("policy_timing"), "tianji_command": None}, ensure_ascii=False, indent=2) + "\n")
    print(f"saved {actions.shape} {actions.dtype} finite={np.isfinite(actions).all()}", flush=True)

if __name__ == "__main__":
    main()
