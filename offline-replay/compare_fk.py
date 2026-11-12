import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import linear_sum_assignment
root = Path("/home/nvidia/cph_dev/pi05/offline-replay")
live = root/"evidence/live-right-20261112_150459_559859520"
bodies = {x.get("name"): x for x in ET.parse(
    root/"reference/droid-panda-33ae6a6.xml").getroot().iter("body")}


def panda(q):
    t = np.eye(4)
    for i in range(1, 9):
        b = bodies["panda_link"+str(i)]
        x = np.eye(4)
        x[:3, 3] = np.fromstring(b.get("pos", "0 0 0"), sep=" ")
        quat = np.fromstring(b.get("quat", "1 0 0 0"), sep=" ")
        x[:3, :3] = Rotation.from_quat(np.r_[quat[1:], quat[0]]).as_matrix()
        t = t@x
        if i < 8:
            x = np.eye(4)
            x[:3, :3] = Rotation.from_rotvec([0, 0, q[i-1]]).as_matrix()
            t = t@x
    return t


def tj(q):
    output = []
    for k in range(0, len(q), 256):
        data = [{"q_rad": [[0.]*7,
                           x.tolist()],
                 "dq_rad_s":[[0.]*7,
                [0.]*7],
            "observed_monotonic":0.,
            "now_monotonic":0.,
            "source_progress_verified":True,
            "joint_feedback_valid":True,
            "recorded_input":True} for x in q[k:k+256]]
        p = subprocess.run(
            [
                "/home/nvidia/wsb_ws/build/direct/native/mios_runtime/mios_kinematics_fixture",
                "--evaluate-stdin"],
            input=json.dumps(data),
            text=True,
            capture_output=True,
            check=True)
        result = json.loads(p.stdout)
        if result["sdk_calls"] != 0 or result["hardware_execute"]:
            raise RuntimeError("FK fixture reported control activity")
        output.extend(np.array(v[1]["O_T_endpoint"]) for v in result["results"])
    return np.array(output)


def rel(t0, t):
    t = np.linalg.inv(t0)@t
    return np.r_[t[:3, 3], Rotation.from_matrix(t[:3, :3]).as_rotvec()]


rows = [json.loads(x) for x in (live/"events.jsonl").read_text().splitlines()]
rows = [r for r in rows if "model_response_monotonic" in r]
q = np.array([r["state"]["joint"]["q_rad"] for r in rows])
d = np.stack([np.cumsum(.2 *
                        np.clip(np.load(live /
                                        f"actions-{r['frame']:06d}.npy")[:3, :7], -
                                1, 1), axis=0) for r in rows])
limits = np.array([np.fromstring(bodies[f"panda_link{i}"].find(
    "joint").get("range"), sep=" ") for i in range(1, 8)])
mask = ((q[:, None, :]+d >= limits[:, 0]) & (q[:, None, :]+d <= limits[:, 1])
        ).all(axis=(1, 2)) & ((q >= limits[:, 0]) & (q <= limits[:, 1])).all(axis=1)
q = q[mask]
d = d[mask]
rows = [r for r, m in zip(rows, mask) if m]
p0 = np.array([panda(x) for x in q])
t0 = tj(q)
ref = np.array([[rel(p0[i], panda(q[i]+dd)) for dd in d[i]] for i in range(len(q))])
direct = np.array([[rel(t0[i], t) for t in tj(q[i]+d[i])] for i in range(len(q))])
mid = q.mean(axis=0)
p = panda(mid)
eps = 1e-5
jf = np.stack([rel(p, panda(mid+np.eye(7)[i]*eps))/eps for i in range(7)], axis=1)
ts = tj(np.array([mid]+[mid+np.eye(7)[i]*eps for i in range(7)]))
jt = np.stack([rel(ts[0], ts[i+1])/eps for i in range(7)], axis=1)
w = np.array([1, 1, 1, .15, .15, .15])[:, None]
a = jf*w
b = jt*w
cost = np.zeros((7, 7))
scale = np.zeros((7, 7))
for i in range(7):
    for j in range(7):
        scale[i, j] = np.clip(a[:, i]@b[:, j]/(b[:, j]@b[:, j]), -3, 3)
        cost[i, j] = np.linalg.norm(a[:, i]-scale[i, j]*b[:, j])**2
ii, jj = linear_sum_assignment(cost)
M = np.zeros((7, 7))
for i, j in zip(ii, jj):
    M[j, i] = scale[i, j]
mapped = np.array([[rel(t0[i], t) for t in tj(q[i]+d[i]@M.T)] for i in range(len(q))])


def stats(y):
    err = np.linalg.norm(ref[:, :, :3]-y[:, :, :3], axis=2)*1000
    angles = [np.degrees((Rotation.from_rotvec(a).inv()*Rotation.from_rotvec(b)).magnitude())
              for a, b in zip(ref[:, :, 3:].reshape(-1, 3), y[:, :, 3:].reshape(-1, 3))]
    return {
        "translation_error_mm_median": float(
            np.median(err)), "translation_error_mm_p95": float(
            np.percentile(
                err, 95)), "rotation_error_deg_median": float(
                    np.median(angles)), "rotation_error_deg_p95": float(
                        np.percentile(
                            angles, 95))}


s = {"valid_blocks": len(q), "excluded_blocks": 48-len(q), "steps": 3, "direct": stats(direct), "signed_permutation": stats(mapped), "matrix": M.tolist(), "reference_first": ref[0, -1].tolist(), "direct_first": direct[0, -1].tolist(), "mapping_first": mapped[0, -1].tolist(
), "frame_first": rows[0]["frame"], "assumptions": "same numeric initial q is hypothetical; local flange frames assumed aligned, 0.2 rad per action step; no collision or calibration; nominal model only; one Jacobian fit, angular weight 0.15m/rad"}
parser = argparse.ArgumentParser(description="Offline Panda and Tianji flange FK comparison")
parser.add_argument("--out", type=Path, required=True, help="New output directory")
args = parser.parse_args()
out = args.out
out.mkdir(parents=True, exist_ok=False)
(out/"summary.json").write_text(json.dumps(s, indent=2)+"\n")
pinv = np.linalg.pinv(jt*w, rcond=.02)
candidate = q[:, None, :]+np.einsum("ij,bkj->bki", pinv, ref*w.reshape(6))
actual = np.array([[rel(t0[i], t) for t in tj(candidate[i])] for i in range(len(q))])
lower = np.array([-170, -120, -170, -140, -170, -60, -90])
upper = np.array([170, 120, 170, 78, 170, 60, 90])
degrees = np.degrees(candidate)
bad = (degrees < lower) | (degrees > upper)
cartesian = {"method": "single linear weighted Jacobian pseudoinverse, rcond 0.02; solve each Panda flange relative pose from fixed common start; exact Tianji FK evaluation",
             "sample_count": int(candidate.shape[0]*candidate.shape[1]),
             "metrics": stats(actual),
             "position_violation_samples": int(bad.any(axis=2).sum()),
             "position_violation_blocks": int(bad.any(axis=(1,
                                                            2)).sum()),
             "max_joint_delta_deg": float(np.max(np.abs(np.degrees(candidate-q[:,
                                                                               None,
                                                                               :])))),
             "no_coupling_collision_or_trajectory_limits_checked": True}
(out/"cartesian-reference.json").write_text(json.dumps(cartesian, indent=2)+"\n")
print(json.dumps({"direct": s["direct"],
                  "signed_permutation": s["signed_permutation"],
                  "cartesian": cartesian["metrics"]}))
