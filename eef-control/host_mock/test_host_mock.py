#!/usr/bin/env python3
import json
import math
import pathlib
import sys
from host_mock import HOST, action_from_ik, run_action

module_names = ("rclpy", "rclpy.node", "geometry_msgs", "marvin_msgs", "sensor_msgs", "std_msgs")
before = {name: sys.modules.get(name) for name in module_names}
q = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7]
valid = run_action({"control_mode": "joint", "jointcmd_right": q, "gripper_right": 0.25})
assert valid == {"accepted": True, "ack": [{"success": True, "control_mode": "joint"}],
                 "ik_requests": 0, "joint_left": [], "joint_right": [q], "gripper_left": [], "gripper_right": [0.25]}
invalid = []
for payload in ({"jointcmd_right": q[:6], "gripper_right": 0.25},
                {"jointcmd_right": q[:6] + [float("nan")], "gripper_right": 0.25},
                {"jointcmd_right": ["bad"] * 7, "gripper_right": 0.25}):
    result = run_action(payload)
    assert result["accepted"] and len(result["ack"]) == 1 and result["ack"][0]["success"] is False
    assert not any(result[k] for k in ("joint_left", "joint_right", "gripper_left", "gripper_right"))
    invalid.append({"ack": result["ack"], "no_publishes": True})
assert all(sys.modules.get(name) is before[name] for name in module_names)
nan_result = run_action({"jointcmd_right": q, "gripper_right": float("nan")})
nan_published = bool(nan_result["gripper_right"]) and math.isnan(nan_result["gripper_right"][0])
ik = {"ok": True, "jointcmd_right": q, "gripper_right": 0.25, "position_error_m": 0.001}
assert action_from_ik(ik) == {"control_mode": "joint", "jointcmd_right": q, "gripper_right": 0.25}
try:
    action_from_ik({"ok": True, "jointcmd_right": q, "gripper_right": float("nan")})
except ValueError:
    pass
else:
    raise AssertionError("nonfinite gripper accepted")
try:
    action_from_ik({"ok": False})
except ValueError:
    pass
else:
    raise AssertionError("failed IK accepted")
result = {"host_source": str(HOST), "host_source_mtime_ns": HOST.stat().st_mtime_ns,
          "route": "installed FastAPI ASGI websocket route /ws/action?ack=true with in-memory events",
          "valid": valid, "invalid_length_nonfinite_type": invalid,
          "nonfinite_gripper_observation": {"ack": nan_result["ack"], "nan_published": nan_published, "note": "accepting nonfinite values is a Host defect, not expected behavior"},
          "ros_stub_modules_restored": True,
          "ik_action_mapping": "success only, jointcmd_right and optional finite gripper_right; diagnostics omitted",
          "scope": "fake messages and publishers; no ROS runtime, device, network or robot"}
print(json.dumps(result, indent=2, allow_nan=False))
