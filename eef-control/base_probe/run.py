#!/usr/bin/env python3
"""Offline pi05_base raw-output probe; no established EEF decoding."""
import argparse
import dataclasses
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVATION = ROOT / "offline-replay/evidence/real-right-20261112_144023_243023462/observation.npz"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "weights/pi05_base")
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION)
    parser.add_argument("--output-dir", type=Path, required=True, help="Existing directory for base-probe.json and base-probe.npz")
    args = parser.parse_args()
    checkpoint, observation, out = args.checkpoint.resolve(), args.observation.resolve(), args.output_dir.resolve()
    if not (checkpoint / "params").is_dir() or not (checkpoint / "assets/droid/norm_stats.json").is_file():
        parser.error("checkpoint must contain params and assets/droid/norm_stats.json")
    if not observation.is_file():
        parser.error("observation file does not exist")
    if not out.is_dir():
        parser.error("output directory must already exist")
    summary, chunks = out / "base-probe.json", out / "base-probe.npz"
    if summary.exists() or chunks.exists():
        parser.error("output already exists; choose a fresh directory")
    os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
    os.environ.setdefault("OPENPI_DATA_HOME", str(ROOT / "jax-sm87/cache/openpi"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    sys.path[:0] = [str(ROOT / "openpi/src"), str(ROOT / "openpi/packages/openpi-client/src")]
    import jax
    import jax.numpy as jnp
    import numpy as np
    from openpi import transforms
    from openpi.models import model as model_lib
    from openpi.models.pi0_config import Pi0Config
    from openpi.policies import policy
    from openpi.shared import normalize
    from openpi.training import config

    with np.load(observation, allow_pickle=False) as src:
        obs = {"observation/exterior_image_1_left": src["exterior_rgb"],
               "observation/wrist_image_left": src["wrist_rgb"],
               "observation/joint_position": src["joint_position"],
               "observation/gripper_position": src["gripper_position"]}
    cfg = dataclasses.replace(config.get_config("pi05_droid"), model=Pi0Config(pi05=True))
    start = time.monotonic()
    model = cfg.model.load(model_lib.restore_params(checkpoint / "params", dtype=jnp.bfloat16))
    data = cfg.data.create(cfg.assets_dirs, cfg.model)
    stats = normalize.load(checkpoint / "assets/droid")
    agent = policy.Policy(model, transforms=[transforms.InjectDefaultPrompt(None),
        *data.data_transforms.inputs, transforms.Normalize(stats, use_quantiles=data.use_quantile_norm),
        *data.model_transforms.inputs], output_transforms=[], sample_kwargs={"num_steps": 10})
    load_seconds = time.monotonic() - start
    noise = np.random.default_rng(0).standard_normal((50, 32)).astype(np.float32)
    task = "pick the orange and place it on the black mouse pad"
    prompts = {"plain": task, "world_eef": "<control_mode> end effector </control_mode> " + task,
               "wrist_eef": "<control_mode> end effector cam frame </control_mode> " + task}
    raw, runs = {}, []
    for name, prompt in prompts.items():
        t = time.monotonic()
        action = np.asarray(agent.infer({**obs, "prompt": prompt}, noise=noise)["actions"])
        if action.shape != (50, 32) or not np.isfinite(action).all():
            raise ValueError(f"invalid {name} output shape or values: {action.shape}")
        raw[name] = action
        runs.append({"name": name, "prompt": prompt, "shape": list(action.shape),
                     "dtype": str(action.dtype), "finite": True, "seconds": time.monotonic() - t})
        print(json.dumps(runs[-1]), flush=True)
    np.savez_compressed(chunks, noise=noise, **raw)
    report = {"status": "raw_only_no_pose_decode", "checkpoint": str(checkpoint), "observation": str(observation),
        "input_mapping": "experimental DROID transform and base droid state quantiles; not proven Tianji or EEF contract",
        "output": "raw normalized 50x32; no action unnormalization, pose decoding, IK or hardware",
        "prompt_source": "https://github.com/Physical-Intelligence/openpi/discussions/302 (pi0; pi05 mode unverified)",
        "tokenizer_note": "control_mode underscore replaced by space during tokenization",
        "noise": "numpy default_rng seed 0, same noise across prompts", "sampling_steps": 10,
        "load_seconds": load_seconds, "runs": runs,
        "comparison": {k: {"mean_abs": float(np.abs(raw[k]-raw["plain"]).mean()),
                            "max_abs": float(np.abs(raw[k]-raw["plain"]).max())} for k in ("world_eef", "wrist_eef")},
        "raw_file": str(chunks), "devices": [str(d) for d in jax.devices()],
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "elapsed_seconds": time.monotonic() - start}
    summary.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {summary} and {chunks}", flush=True)


if __name__ == "__main__":
    main()
