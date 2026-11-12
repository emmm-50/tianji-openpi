#!/usr/bin/env python3
"""Run the official pi05_droid JAX policy on a synthetic observation."""
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
os.environ.setdefault("XLA_FLAGS", "--xla_gpu_autotune_level=0")
os.environ.setdefault("OPENPI_DATA_HOME", str(ROOT / "cache/openpi"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path[:0] = [str(ROOT / "openpi/src"), str(ROOT / "openpi/packages/openpi-client/src")]

import jax
import jax.numpy as jnp
import numpy as np
from openpi import transforms
from openpi.models import model as model_lib
from openpi.policies import droid_policy, policy
from openpi.shared import normalize
from openpi.training import config


def memory():
    result = {"process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    result["devices"] = [{"device": str(d), "memory_stats": d.memory_stats()} for d in jax.devices()]
    return result


def main():
    start = time.monotonic()
    checkpoint = ROOT / "weights/pi05_droid"
    cfg = config.get_config("pi05_droid")
    # Same JAX branch and transform order as create_trained_policy; importing
    # training.checkpoints would also import the unrelated training data loader.
    model = cfg.model.load(model_lib.restore_params(checkpoint / "params", dtype=jnp.bfloat16))
    data = cfg.data.create(cfg.assets_dirs, cfg.model)
    stats = normalize.load(checkpoint / "assets" / data.asset_id)
    agent = policy.Policy(model, transforms=[
        transforms.InjectDefaultPrompt(None),
        *data.data_transforms.inputs,
        transforms.Normalize(stats, use_quantiles=data.use_quantile_norm),
        *data.model_transforms.inputs,
    ], output_transforms=[
        *data.model_transforms.outputs,
        transforms.Unnormalize(stats, use_quantiles=data.use_quantile_norm),
        *data.data_transforms.outputs,
    ], metadata=cfg.policy_metadata)
    load_seconds = time.monotonic() - start
    print(f"model loaded in {load_seconds:.3f}s", flush=True)
    result = {"config": cfg.name, "devices": [str(d) for d in jax.devices()],
              "load_seconds": load_seconds, "after_load": memory(), "runs": []}
    np.random.seed(0)
    observation = droid_policy.make_droid_example()
    for label in ("first", "warm"):
        start = time.monotonic()
        output = agent.infer(observation)
        elapsed = time.monotonic() - start
        actions = output["actions"]
        run = {"label": label, "seconds": elapsed, "shape": list(actions.shape),
               "dtype": str(actions.dtype), "finite": bool(np.isfinite(actions).all()),
               "policy_timing": output.get("policy_timing"), "memory": memory()}
        result["runs"].append(run)
        print(json.dumps(run), flush=True)
    path = ROOT / "cache/offline_result.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"result: {path}", flush=True)


if __name__ == "__main__":
    main()
