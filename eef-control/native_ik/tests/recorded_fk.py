"""Read recorded joint feedback and calculate independent shared-URDF FK offline."""
import bisect
import json
import os
from pathlib import Path

import numpy as np
import pinocchio as pin
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT.parents[2] / "gr00t-tianji" / "recording" / "provenance.json"
JOINT_NAMES = [f"Joint{j}_{side}" for side in "LR" for j in range(1, 8)]


def recorded_states(bag=None, provenance=None):
    with open(provenance or os.environ.get("TIANJI_FIXTURE_PROVENANCE") or PROVENANCE) as f:
        meta = json.load(f)
    if bag is None:
        bag = str(Path(os.environ.get("TIANJI_BAG") or meta["bag"]) / "data")
    times = meta["bag_timestamps_ns"]
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id="mcap"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    topic = "/tj/joint_states"
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types() if t.name == topic}
    reader.set_filter(rosbag2_py.StorageFilter(topics=[topic]))
    samples = []
    while reader.has_next():
        _, raw, stamp = reader.read_next()
        if stamp > times[-1]:
            break
        samples.append((stamp, deserialize_message(raw, types[topic])))
    stamps = [sample[0] for sample in samples]
    result = []
    for frame, time in zip(meta["source_video_frames"], times):
        index = bisect.bisect_right(stamps, time) - 1
        if index < 0:
            raise ValueError(f"no joint feedback for frame {frame}")
        stamp, msg = samples[index]
        if len(set(msg.name)) != len(msg.name):
            raise ValueError("duplicate joint names")
        q = [float(msg.position[msg.name.index(name)]) for name in JOINT_NAMES]
        header_ns = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
        result.append({"frame": frame, "video_ns": time, "joint_ns": stamp, "header_stamp_ns": header_ns or None, "q": q})
    return result


def urdf_fk(q):
    """Return APEX-world right_tool xyz and xyzw; finger joints fixed at zero."""
    model = pin.buildModelFromUrdf(str(ROOT / "robot_model/urdf/Pro-m6-696.urdf"))
    config = pin.neutral(model)
    for name, value in zip(JOINT_NAMES, q):
        config[model.joints[model.getJointId(name)].idx_q] = value
    data = model.createData()
    pin.forwardKinematics(model, data, config)
    pin.updateFramePlacements(model, data)
    pose = data.oMf[model.getFrameId("right_tool")]
    rotation = pin.rpy.rpyToMatrix(0., 0., np.pi / 2)
    return (rotation @ pose.translation).tolist(), pin.Quaternion(rotation @ pose.rotation).coeffs().tolist()
