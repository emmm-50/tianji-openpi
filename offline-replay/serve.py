#!/usr/bin/env python3
"""Warm a DROID policy on a saved observation, then serve inference on loopback."""
import argparse
import logging
from pathlib import Path

import numpy as np

from replay import build_policy, load_observation
from openpi.serving.websocket_policy_server import WebsocketPolicyServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("observation", type=Path, help="saved NPZ used to warm the policy")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    obs, _ = load_observation(args.observation)
    logging.info("Loading policy")
    agent = build_policy()
    logging.info("Warming policy")
    result = agent.infer(obs)
    actions = result["actions"]
    if actions.shape != (15, 8) or not np.isfinite(actions).all():
        raise ValueError(f"invalid warmup output: shape={actions.shape}")
    logging.info("Warmup complete; serving on 127.0.0.1:%d", args.port)
    WebsocketPolicyServer(agent, host="127.0.0.1", port=args.port,
                          metadata=agent.metadata).serve_forever()


if __name__ == "__main__":
    main()
