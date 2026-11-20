"""Run recorded FK targets through the offline solver, never a hardware interface."""
import json
import os
import sys
import numpy as np
from recorded_fk import ROOT, recorded_states, urdf_fk

sys.path.insert(0, str(ROOT.parent / "host_mock"))
from ik_adapter import DT_NS, IKAdapter, NativeSolver

binary = sys.argv[1] if len(sys.argv) > 1 else "/tmp/native-ik-build/native_ik"
with open("/opt/kernelmind/apex/install/marvin_qp_controller/share/marvin_qp_controller/config/m6s_696/velocity_limits.json") as f:
    limits = json.load(f)["velocity_limits"]
velocity = np.array([limits[f"Joint{i}_R"] for i in range(1, 8)])
states = recorded_states()
os.environ["LD_LIBRARY_PATH"] = "/home/nvidia/.local/lib/python3.10/site-packages:" + os.environ.get("LD_LIBRARY_PATH", "")
solver = NativeSolver(binary, str(ROOT / "ik_tasks.yaml"))
previous = np.array(states[0]["q"][7:])
max_ratios = np.zeros(7)
step_count = 0

def checked_solve(payload):
    global previous, max_ratios, step_count
    response = solver(payload)
    if payload["type"] == "step" and response.get("ok"):
        actual = np.array(response["jointcmd_right"])
        ratios = abs(actual - previous) / (velocity * (DT_NS / 1e9))
        max_ratios = np.maximum(max_ratios, ratios)
        ratio = float(max(ratios))
        if ratio > 1.00001:
            raise AssertionError(f"velocity limit ratio {ratio} at solver step {step_count}")
        previous = actual
        step_count += 1
    return response

try:
    adapter = IKAdapter(checked_solve)
    first = states[0]
    adapter.initialize({"stamp": None, "joint_states": {"positions": first["q"]}}, feedback_source_ns=first["header_stamp_ns"], feedback_received_ns=None, plan_start_ns=first["video_ns"] - DT_NS)
    for index, state in enumerate(states):
        position, quaternion = urdf_fk(state["q"])
        count_before = step_count
        result = adapter.step({"position": position, "quaternion_xyzw": quaternion}, observation_id=state["frame"], observation_time_ns=state["video_ns"], target_time_ns=state["video_ns"])
        response = result["ik"]
        joint_difference = float(max(abs(previous - np.array(state["q"][7:]))))
        if index == 0 and joint_difference > 1e-8:
            raise AssertionError(f"frame 300 hold changed right joint order or values: {joint_difference}")
        if response["position_error_m"] > 1e-4 or response["rotation_error_rad"] > 1e-3:
            raise AssertionError(f"frame {state['frame']}: residual {response}")
        print(json.dumps({"frame": state["frame"], "video_ns": state["video_ns"], "joint_ns": state["joint_ns"], "header_stamp_ns": state["header_stamp_ns"], "plan_ns": result["plan_time_ns"], "steps": step_count - count_before, "position_error_m": response["position_error_m"], "rotation_error_rad": response["rotation_error_rad"], "max_joint_difference_rad": joint_difference}), flush=True)
finally:
    solver.close()
print(json.dumps({"max_velocity_rad_s": (max_ratios * velocity).tolist(), "velocity_limits_rad_s": velocity.tolist(), "max_velocity_limit_ratio": float(max(max_ratios)), "hardware_commands_sent": False}))
