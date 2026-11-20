#!/usr/bin/env python3
"""Recorded feedback and FK -> native IK -> installed Host, offline only."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "native_ik/tests"))
from recorded_fk import recorded_states, urdf_fk
from ik_adapter import IKAdapter, NativeSolver
from host_mock import run_action, load_host
from marvin_msgs.msg import JointcmdArm, Jointfeedback
from rclpy.serialization import serialize_message, deserialize_message

solver = NativeSolver(*sys.argv[1:3])
try:
    states = recorded_states()
    state, later = states[:2]
    position, quat = urdf_fk(state["q"])
    adapter = IKAdapter(solver)
    snapshot = {"stamp": None, "joint_states": {"positions": state["q"]}}
    adapter.initialize(snapshot, feedback_source_ns=state["header_stamp_ns"],
                       feedback_received_ns=state["joint_ns"],
                       plan_start_ns=state["video_ns"])
    target = {"position": position, "quaternion_xyzw": quat}
    def step(pose, end_ns):
        return adapter.step(pose, observation_id=state["frame"],
                            observation_time_ns=state["video_ns"], target_time_ns=end_ns)

    start = state["video_ns"]
    hold = step(target, start + 66_666_667)
    delta = max(abs(a-b) for a, b in zip(hold["action"]["jointcmd_right"], state["q"][7:]))
    assert delta < 1e-5, delta
    assert hold["plan_time_ns"] == start + 66_000_000

    # Treat index 0 as the start of the first 15 Hz interval, index 1 as the next.
    moved_position, moved_quat = urdf_fk(later["q"])
    assert max(abs(a-b) for a, b in zip(moved_position, position)) > 1e-5
    moved = step({"position": moved_position, "quaternion_xyzw": moved_quat},
                 start + 133_333_334)
    assert moved["plan_time_ns"] == start + 132_000_000
    assert max(abs(a-b) for a, b in zip(moved["action"]["jointcmd_right"],
                                       hold["action"]["jointcmd_right"])) > 1e-8
    capture = run_action(moved["action"])
    assert capture["ack"] == [{"success": True, "control_mode": "joint"}]
    assert capture["joint_right"] == [moved["action"]["jointcmd_right"]]
    assert capture["ik_requests"] == 0
    assert not capture["joint_left"] and not capture["gripper_left"]
    assert not capture["gripper_right"]

    cmd = JointcmdArm()
    cmd.positions = capture["joint_right"][0]
    decoded_cmd = deserialize_message(serialize_message(cmd), JointcmdArm)
    assert list(decoded_cmd.positions) == capture["joint_right"][0]
    feedback = Jointfeedback()
    feedback.header.stamp.sec, feedback.header.stamp.nanosec = 42, 100
    feedback.arm_positions = state["q"][:7] + list(decoded_cmd.positions)
    feedback = deserialize_message(serialize_message(feedback), Jointfeedback)
    readback = load_host().VlaHostNode._joint_state_to_dict(None, feedback)
    source_ns = feedback.header.stamp.sec * 1_000_000_000 + feedback.header.stamp.nanosec
    received_ns, snapshot_ns = 42_000_000_250, 42_000_000_300
    adapter.initialize({"stamp": snapshot_ns, "joint_states": readback},
                       feedback_source_ns=source_ns, feedback_received_ns=received_ns,
                       plan_start_ns=start)
    # FK of the decoded simulated feedback is the hold target for the new run.
    feedback_position, feedback_quat = urdf_fk(readback["positions"])
    feedback_hold = step({"position": feedback_position, "quaternion_xyzw": feedback_quat},
                         start + 2_000_000)
    assert feedback_hold["feedback"] == {"source_ns": source_ns,
        "received_ns": received_ns, "snapshot_stamp_ns": snapshot_ns}
    assert max(abs(a-b) for a, b in zip(feedback_hold["action"]["jointcmd_right"],
                                       readback["positions"][7:])) < 1e-5

    for invalid in ({**target, "gripper_right": "NaN"},
                    {**target, "quaternion_xyzw": [1e308, 0, 0, 1e308]},
                    {**target, "quaternion_xyzw": [0, 0, 0, 0]}):
        adapter.initialize(snapshot, feedback_source_ns=state["header_stamp_ns"],
                           feedback_received_ns=state["joint_ns"], plan_start_ns=start)
        try:
            step(invalid, start + 2_000_000)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid target accepted")
        try:
            step(target, start + 2_000_000)
        except ValueError:
            pass
        else:
            raise AssertionError("failed IK left adapter initialized")
    # Direct JSONL callers also discard a previous seed after a rejected init.
    assert solver({"type": "init", "q": state["q"]})["ok"]
    outside_limits = state["q"].copy()
    outside_limits[1] = 3.0
    rejected = solver({"type": "init", "q": outside_limits})
    assert not rejected["ok"] and "jointcmd_right" not in rejected
    next_step = solver({"type": "step", **target})
    assert next_step == {"ok": False, "error": "init required"}

    print(json.dumps({"frames": [state["frame"], later["frame"]],
        "bag_receive_ns": [state["joint_ns"], later["joint_ns"]],
        "max_hold_delta_rad": delta, "capture": capture,
        "feedback_association": feedback_hold["feedback"],
        "invalid_targets_blocked": 3}))
finally:
    solver.close()
