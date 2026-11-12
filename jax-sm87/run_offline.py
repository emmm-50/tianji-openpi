#!/usr/bin/env python3
"""Run the official pi05_droid JAX policy on a synthetic observation."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
os.environ.setdefault("OPENPI_DATA_HOME", str(Path(__file__).resolve().parent / "cache/openpi"))
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "evidence/offline_result.json")
    args = parser.parse_args()
    num_steps = 10
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
    ], metadata=cfg.policy_metadata, sample_kwargs={"num_steps": num_steps})
    load_seconds = time.monotonic() - start
    print(f"model loaded in {load_seconds:.3f}s", flush=True)
    result = {"config": cfg.name, "python": sys.executable, "jax_version": jax.__version__,
              "xla_flags": os.environ.get("XLA_FLAGS"), "checkpoint": str(checkpoint),
              "versions": {p: importlib.metadata.version(p) for p in ("jax", "jaxlib", "jax-cuda12-plugin", "jax-cuda12-pjrt")},
              "environment": {k: os.environ.get(k) for k in ("LD_LIBRARY_PATH", "XLA_PYTHON_CLIENT_PREALLOCATE", "OPENPI_DATA_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}, "num_steps": num_steps, "devices": [str(d) for d in jax.devices()],
              "load_seconds": load_seconds, "after_load": memory(), "runs": []}
    np.random.seed(0)
    observation = droid_policy.make_droid_example()
    for i in range(args.warmup_runs + args.runs):
        label = "warmup" if i < args.warmup_runs else "measurement"
        start = time.monotonic()
        output = agent.infer(observation)
        elapsed = time.monotonic() - start
        actions = output["actions"]
        run = {"label": label, "index": i + 1, "seconds": elapsed, "shape": list(actions.shape),
               "dtype": str(actions.dtype), "finite": bool(np.isfinite(actions).all()),
               "policy_timing": output.get("policy_timing"), "memory": memory()}
        result["runs"].append(run)
        print(json.dumps(run), flush=True)
    with open("/proc/self/maps") as maps:
        result["loaded_gpu_libraries"] = sorted({line.split()[-1] for line in maps if any(name in line for name in ("libcudnn", "libcublas", "libcudart", "libcuda.so", "xla_cuda_plugin.so")) and line.split()[-1].startswith("/")})
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    measured = [r["seconds"] for r in result["runs"] if r["label"] == "measurement"]
    if measured:
        summary = {"count": len(measured), "mean_seconds": float(np.mean(measured)), "median_seconds": float(np.median(measured)), "p95_seconds": float(np.percentile(measured, 95, method="linear")), "p95_method": "numpy.percentile linear", "min_seconds": min(measured), "max_seconds": max(measured)}
        summary_path = args.output.with_name(args.output.stem + "-summary.json")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary), flush=True)
    print(f"result: {args.output}", flush=True)


if __name__ == "__main__":
    main()
