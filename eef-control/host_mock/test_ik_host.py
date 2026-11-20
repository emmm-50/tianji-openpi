#!/usr/bin/env python3
"""Run a fixed offline IK fixture through the installed Host handler with fake pubs."""
import json
import subprocess
import sys
from host_mock import action_from_ik, run_action

binary, config = sys.argv[1:3]
q = [0, -0.1, 0, -0.1, 0, 0, 0, -1.845240831375122, -0.8560925722122192,
     1.5991649627685547, -1.8537635803222656, 0.7187421917915344, 0.10505466908216476, -0.3611849844455719]
step = {"type": "step", "position": [0.5023625744864375, -0.39660238091171596, 0.8469407004049634],
        "quaternion_xyzw": [-0.0059703669285189635, 0.07279627724394282, -0.0981977434162663, 0.9924828763893688],
        "gripper_right": 0.5}
moved = {**step, "position": [step["position"][0] + 0.001, *step["position"][1:]]}
invalid = {**step, "gripper_right": "NaN"}
huge_quaternion = {**step, "quaternion_xyzw": [1e308, 0, 0, 1e308]}
input_lines = [{"type": "init", "q": q}, step, moved, invalid, huge_quaternion]
p = subprocess.run([binary, config], input="".join(json.dumps(x) + "\n" for x in input_lines),
                   text=True, capture_output=True, check=True)
responses = [json.loads(line) for line in p.stdout.splitlines()]
assert len(responses) == 5 and all(r["ok"] for r in responses[:3])
assert all(r["ok"] is False and "jointcmd_right" not in r for r in responses[3:])
delta = [a-b for a,b in zip(responses[2]["jointcmd_right"], responses[1]["jointcmd_right"])]
assert max(map(abs, delta)) > 1e-8
action = action_from_ik(responses[2])
capture = run_action(action)
assert capture["ack"] == [{"success": True, "control_mode": "joint"}]
assert capture["joint_right"] == [responses[2]["jointcmd_right"]]
assert capture["gripper_right"] == [0.5] and not capture["joint_left"] and not capture["gripper_left"]
for response in responses[3:]:
    try:
        action_from_ik(response)
    except ValueError:
        pass
    else:
        raise AssertionError("failed IK result reached Host")
print(json.dumps({"scope": "fake EEF fixture to offline native IK to installed Host ASGI websocket route with fake publishers; no network transport, ROS node or robot", "ik_executable": binary,
                  "ik_config": config, "inputs": input_lines, "ik_responses": responses,
                  "target_translation_world_m": [0.001, 0, 0], "joint_delta_from_hold_rad": delta,
                  "max_abs_joint_delta_from_hold_rad": max(map(abs, delta)), "host_action": action, "host_capture": capture,
                  "invalid_ik_response_sent_to_host": False}, indent=2, allow_nan=False))
