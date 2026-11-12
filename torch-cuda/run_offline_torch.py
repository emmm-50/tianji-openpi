#!/usr/bin/env python3
"""Run the official pi05_droid PyTorch policy on the existing seeded dummy observation."""
import dataclasses
import json
import os
from pathlib import Path
import resource
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
WORK = Path(__file__).resolve().parent
os.environ["JAX_PLATFORMS"] = "cpu"
os.environ.setdefault("OPENPI_DATA_HOME", str(ROOT / "cache/openpi"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path[:0] = [str(ROOT / "openpi/src"), str(ROOT / "openpi/packages/openpi-client/src")]

import numpy as np
import torch
from openpi import transforms
from openpi.policies import droid_policy, policy
from openpi.shared import normalize
from openpi.training import config


def memory():
    return {
        "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "cuda_allocated_bytes": torch.cuda.memory_allocated(0),
        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
        "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(0),
    }


def main():
    checkpoint = WORK / "weights/pi05_droid-pytorch"
    start = time.monotonic()
    cfg = config.get_config("pi05_droid")
    cfg = dataclasses.replace(cfg, model=dataclasses.replace(cfg.model, pytorch_compile_mode=None))
    model = cfg.model.load_pytorch(cfg, str(checkpoint / "model.safetensors"))
    model.paligemma_with_expert.to_bfloat16_for_selected_params("bfloat16")
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
    ], sample_kwargs={"num_steps": 10}, metadata=cfg.policy_metadata,
        is_pytorch=True, pytorch_device="cuda:0")
    torch.cuda.synchronize(0)
    result = {
        "config": cfg.name, "torch": torch.__version__, "torch_cuda": torch.version.cuda,
        "device": torch.cuda.get_device_name(0), "capability": list(torch.cuda.get_device_capability(0)),
        "parameter_devices": sorted({str(p.device) for p in model.parameters()}),
        "parameter_dtypes": sorted({str(p.dtype) for p in model.parameters()}),
        "compile_mode": cfg.model.pytorch_compile_mode, "num_steps": 10,
        "load_seconds": time.monotonic() - start, "after_load": memory(), "runs": [],
    }
    np.random.seed(0)
    torch.manual_seed(0)
    observation = droid_policy.make_droid_example()
    with torch.inference_mode():
        for label in ("first", "warm"):
            torch.cuda.synchronize(0)
            start = time.monotonic()
            output = agent.infer(observation)
            torch.cuda.synchronize(0)
            actions = output["actions"]
            run = {"label": label, "seconds": time.monotonic() - start,
                   "shape": list(actions.shape), "dtype": str(actions.dtype),
                   "finite": bool(np.isfinite(actions).all()), "memory": memory()}
            result["runs"].append(run)
            print(json.dumps(run), flush=True)
    path = WORK / "evidence/offline_torch_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"result: {path}", flush=True)


if __name__ == "__main__":
    main()
