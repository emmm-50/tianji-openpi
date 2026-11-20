#!/usr/bin/env python3
"""Offline synthetic mapping experiment; never use as a robot policy decoder."""
import json
import pathlib
import subprocess
import sys
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = pathlib.Path("/home/nvidia/cph_dev/pi05")
sys.path.insert(0, str(ROOT / "eef-control/host_mock"))
from host_mock import action_from_ik, run_action

SOURCE = ROOT / "evidence/base-eef-ik-20261119/base-actual-20261120.npz"
OUT = ROOT / "evidence/base-eef-ik-20261119"
Q0 = np.array([0, -0.1, 0, -0.1, 0, 0, 0, -1.845240831375122, -0.8560925722122192,
               1.5991649627685547, -1.8537635803222656, 0.7187421917915344, 0.10505466908216476, -0.3611849844455719])
P0 = np.array([0.5023625744864375, -0.39660238091171596, 0.8469407004049634])
R0 = Rotation.from_quat([-0.0059703669285189635, 0.07279627724394282, -0.0981977434162663, 0.9924828763893688])

class FakeSDK:
    def __init__(self):
        self.joints = Q0.copy()
        self.gripper = None
        self.write_count = 0
    def apply_joint_command_rad(self, right, gripper):
        self.write_count += 1
        self.joints[7:] = right
        self.gripper = gripper
    def read(self):
        return self.joints.copy(), self.gripper


def request(process, message):
    process.stdin.write(json.dumps(message, allow_nan=False) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("IK closed unexpectedly")
    return json.loads(line)


def main(binary):
    with np.load(SOURCE, allow_pickle=False) as data:
        raw = data["world_eef"].astype(float)
    if raw.shape != (50, 32) or not np.isfinite(raw).all():
        raise ValueError("invalid saved raw array")
    fake = FakeSDK()
    targets, poses, commands, readbacks, grippers, residuals = [], [], [], [], [], []
    config = ROOT / "eef-control/native_ik/ik_tasks.yaml"
    proc = subprocess.Popen([binary, str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        initialized = request(proc, {"type": "init", "q": Q0.tolist()})
        assert initialized["ok"]
        for frame in raw:
            p = P0 + 0.01 * np.tanh(frame[:3])
            rotvec = 0.05 * np.tanh(frame[3:6])
            quat = (Rotation.from_rotvec(rotvec) * R0).as_quat()
            grip = float((np.tanh(frame[6]) + 1) / 2)
            result = request(proc, {"type": "step", "position": p.tolist(),
                                    "quaternion_xyzw": quat.tolist(), "gripper_right": grip})
            action = action_from_ik(result)
            capture = run_action(action)
            assert capture["ack"] == [{"success": True, "control_mode": "joint"}]
            assert capture["joint_right"] == [result["jointcmd_right"]]
            assert capture["gripper_right"] == [grip]
            assert not capture["joint_left"] and not capture["gripper_left"]
            fake.apply_joint_command_rad(capture["joint_right"][0], capture["gripper_right"][0])
            q, g = fake.read()
            assert np.array_equal(q[:7], Q0[:7]) and np.array_equal(q[7:], result["jointcmd_right"]) and g == grip
            targets.append(p); poses.append(quat); commands.append(result["jointcmd_right"])
            readbacks.append(q); grippers.append(g)
            residuals.append([result["position_error_m"], result["rotation_error_rad"]])
        before_q, before_g = fake.read()
        before_count = fake.write_count
        invalid = request(proc, {"type": "step", "position": P0.tolist(),
                        "quaternion_xyzw": R0.as_quat().tolist(), "gripper_right": "NaN"})
        invalid_pose = request(proc, {"type": "step", "position": P0.tolist(),
                               "quaternion_xyzw": [1e308, 0, 0, 1e308]})
        assert all(r["ok"] is False and "jointcmd_right" not in r for r in (invalid, invalid_pose))
        for response in (invalid, invalid_pose, {"ok": True, "jointcmd_right": Q0[7:].tolist(), "gripper_right": float("nan")}):
            try:
                action_from_ik(response)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid response passed to Host")
        after_q, after_g = fake.read()
        assert np.array_equal(before_q, after_q) and before_g == after_g and before_count == fake.write_count
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(f"IK exited {proc.returncode}")
    commands, readbacks, residuals = np.array(commands), np.array(readbacks), np.array(residuals)
    assert np.max(np.abs(commands - Q0[7:])) > 1e-8
    trace = OUT / "virtual-sdk-20261120.npz"
    np.savez_compressed(trace, target_position=np.array(targets), target_quaternion_xyzw=np.array(poses),
                        jointcmd_right=commands, sdk_joint_readback=readbacks,
                        gripper=np.array(grippers), ik_residuals=residuals)
    result = {"scope": "synthetic offline software plumbing only; not pi05 EEF decoding, robot success or dynamics",
              "source": str(SOURCE), "source_array": "world_eef", "source_shape": list(raw.shape),
              "synthetic_mapping": {"position": "p0 + 0.01*tanh(raw[0:3]) metres; each world axis bounded by 0.01 m, norm up to sqrt(3)*0.01 m",
                 "orientation": "Rotation.from_rotvec(0.05*tanh(raw[3:6])) * R0; world-axis left multiplication, each rotvec component bounded by 0.05 rad",
                 "gripper": "(tanh(raw[6])+1)/2, dimensionless mock only",
                 "caveat": "channels, scales and modes are invented for this test; not an official base model contract"},
              "ik": "existing offline native IK, one 2 ms solver step per source frame; no physical timing",
              "frames": len(commands), "host_success_ack_count": len(commands), "fake_sdk_write_count": fake.write_count,
              "transport": "50 separate in-memory ASGI calls; saved chunk open-loop replay, no new observations or inference",
              "host_right_command_equals_sdk_readback": True, "left_arm_unchanged": True,
              "gripper_host_equals_sdk": True, "invalid_ik_and_nonfinite_gripper_no_sdk_update": True,
              "invalid_ik_responses": [invalid, invalid_pose],
              "max_joint_change_from_initial_rad": float(np.max(np.abs(commands-Q0[7:]))),
              "max_position_residual_m": float(residuals[:,0].max()),
              "max_rotation_residual_rad": float(residuals[:,1].max()),
              "fake_sdk": "in-memory direct radian assignments; not vendor SDK ABI, ROS or dynamics",
              "trace": str(trace)}
    (OUT / "virtual-sdk-20261120.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main(sys.argv[1])
