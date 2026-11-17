#!/usr/bin/env python3
"""Sample right-arm mesh collisions using the vendor CAD URDF and hpp-fcl."""
import argparse
import json
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path

import hppfcl
import numpy as np
from scipy.spatial.transform import Rotation

DEFAULT_MODEL_DIR = (Path(__file__).resolve().parents[2] /
                     "tianji-robot-resources/resources/marvin/models/Pro-m6-696")

def origin(element):
    out = np.eye(4)
    if element is not None:
        out[:3, 3] = np.fromstring(element.get("xyz", "0 0 0"), sep=" ")
        out[:3, :3] = Rotation.from_euler("xyz", np.fromstring(element.get("rpy", "0 0 0"), sep=" ")).as_matrix()
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples-per-segment", type=int, default=10)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR,
                        help="Pro-m6-696 model directory containing urdf/ and meshes/")
    args = parser.parse_args()
    model_dir = args.model_dir.expanduser().resolve()
    urdf = model_dir / "urdf/Pro-m6-696.urdf"
    root = ET.parse(urdf).getroot()
    joints = {joint.get("name"): joint for joint in root.findall("joint")}
    base_joint = joints["base_to_right_arm"]
    if (base_joint.get("type") != "fixed" or
            base_joint.find("parent").get("link") != "base_link" or
            base_joint.find("child").get("link") != joints["Joint1_R"].find("parent").get("link")):
        raise ValueError("Expected base_to_right_arm to connect base_link to the Joint1_R parent")
    arm_base = origin(base_joint.find("origin"))
    links = {link.get("name"): link for link in root.findall("link")}
    names = ["base_link"] + [f"Link{i}_R" for i in range(1, 8)]
    loader = hppfcl.MeshLoader()
    meshes = {}
    local = {}
    for name in names:
        col = links[name].find("collision")
        mesh = col.find("geometry/mesh")
        path = model_dir / mesh.get("filename").split("package://Pro-m6-696/", 1)[1]
        meshes[name] = loader.load(str(path))
        local[name] = origin(col.find("origin"))
    pairs = [(a, b) for a, b in combinations(names, 2) if abs(names.index(a) - names.index(b)) > 1]
    request = hppfcl.CollisionRequest()
    data = json.loads(args.trajectory.read_text())
    results = []
    for record in data["records"]:
        if not record["retarget_pass"]:
            results.append({"frame": record["frame"], "checked": False, "reason": "retarget failed"})
            continue
        points = np.asarray(record["waypoints_rad"], dtype=float)
        samples = [points[0]]
        for start, end in zip(points[:-1], points[1:]):
            samples.extend(start + (end - start) * k / args.samples_per_segment
                           for k in range(1, args.samples_per_segment + 1))
        collisions = []
        for index, q in enumerate(samples):
            poses = {"base_link": np.eye(4)}
            parent = arm_base.copy()
            for i in range(1, 8):
                joint = joints[f"Joint{i}_R"]
                parent = parent @ origin(joint.find("origin"))
                axis = np.fromstring(joint.find("axis").get("xyz"), sep=" ")
                rot = np.eye(4)
                rot[:3, :3] = Rotation.from_rotvec(axis * q[i - 1]).as_matrix()
                parent = parent @ rot
                poses[f"Link{i}_R"] = parent.copy()
            objects = {}
            for name in names:
                transform = poses[name] @ local[name]
                objects[name] = hppfcl.CollisionObject(meshes[name], hppfcl.Transform3f(transform[:3, :3], transform[:3, 3]))
            hits = [f"{a}/{b}" for a, b in pairs
                    if hppfcl.collide(objects[a], objects[b], request, hppfcl.CollisionResult())]
            if hits:
                collisions.append({"sample_index": index, "pairs": hits})
        results.append({"frame": record["frame"], "checked": True, "samples": len(samples), "collisions": collisions})
    args.out.mkdir(parents=True, exist_ok=False)
    summary = {"scope": "sampled exact triangle mesh intersections for CAD right arm Link1-7 and base; no left arm, wrist, gripper or scene",
               "source_urdf": str(urdf), "samples_per_segment": args.samples_per_segment,
               "excluded_pairs": "direct neighbours only", "continuous_collision_proven": False,
               "model_to_physical_registration_verified": False, "records": results}
    (args.out / "collision.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"checked": sum(x["checked"] for x in results),
                      "colliding": sum(bool(x.get("collisions")) for x in results)}))

if __name__ == "__main__":
    main()
