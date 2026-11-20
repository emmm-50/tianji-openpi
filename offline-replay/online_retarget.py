"""Online read-only numerical retargeting using the verified offline method."""
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


root = Path(__file__).resolve().parent
sys.path.insert(0, "/home/nvidia/wsb_ws/tools")
from review_model_compatibility import config_rows

config = config_rows(Path("/opt/kernelmind/apex/install/marvin_teleop/share/marvin_teleop/config/ccs_m6s_696.MvKDCfg"))[1]
limits = np.asarray(config[1:8])[:, 4:8]
model = ET.parse(root / "reference/droid-panda-33ae6a6.xml")
homes = []
for i in range(1, 9):
    body = model.find(f".//body[@name=\"panda_link{i}\"]")
    pose = np.eye(4)
    pose[:3, 3] = np.fromstring(body.get("pos", "0 0 0"), sep=" ")
    pose[:3, :3] = Rotation.from_quat(np.roll(np.fromstring(body.get("quat", "1 0 0 0"), sep=" "), -1)).as_matrix()
    homes.append(pose)

def panda(q):
    pose = np.eye(4)
    for home, angle in zip(homes, [*q, 0.0]):
        pose = pose @ home
        pose[:3, :3] = pose[:3, :3] @ Rotation.from_rotvec([0, 0, angle]).as_matrix()
    return pose

def fk(q):
    samples = [dict(q_rad=[[0.]*7,x.tolist()], dq_rad_s=[[0.]*7]*2, observed_monotonic=0, now_monotonic=0, source_progress_verified=True, joint_feedback_valid=True, recorded_input=True) for x in q]
    cmd = "/home/nvidia/wsb_ws/build/direct/native/mios_runtime/mios_kinematics_fixture"
    result = json.loads(subprocess.run([cmd, "--evaluate-stdin"], input=json.dumps(samples), text=True, capture_output=True, check=True).stdout)
    assert result["sdk_calls"] == 0 and not result["hardware_execute"]
    arms = [item[1] for item in result["results"]]
    return np.array([item["O_T_endpoint"] for item in arms]), np.array([item["O_J_endpoint"] for item in arms])

def residual(target, current):
    translation = target[:, :3, 3] - current[:, :3, 3]
    rotation = Rotation.from_matrix(target[:, :3, :3] @ current[:, :3, :3].transpose(0, 2, 1)).as_rotvec()
    return np.column_stack((translation, rotation))

def allowed(q):
    degrees = np.rad2deg(q)
    j6, j7 = degrees[:, 5], degrees[:, 6]
    up, un, ln, lp = [np.polyval(c, j6) for c in config[9:13]]
    return ((degrees >= limits[:,0]) & (degrees <= limits[:,1])).all(axis=1) & (j7 <= np.where(j6 >= 0, up, un)) & (j7 >= np.where(j6 >= 0, lp, ln))


class Retargeter:
    def plan(self, q_rad, actions):
        q0 = np.asarray(q_rad, dtype=float).reshape(1, 7)
        actions = np.asarray(actions, dtype=float)
        if actions.shape != (15, 8) or not np.isfinite(actions).all() or not np.isfinite(q0).all():
            raise ValueError("invalid observation or actions")
        delta = np.cumsum(.2 * np.clip(actions[None, :3, :7], -1, 1), axis=1)
        p0 = np.array([panda(q) for q in q0])
        t0, _ = fk(q0)
        targets = [t0 @ np.linalg.inv(p0) @ np.array([panda(q+d) for q,d in zip(q0,delta[:,step])]) for step in range(3)]
        weights = np.array([1, 1, 1, .15, .15, .15])
        guess = q0.copy()
        positions = [guess.copy()]
        errors = []
        for target in targets:
            for iteration in range(18):
                current, jacobian = fk(guess)
                error = residual(target, current)
                if (np.linalg.norm(error, axis=1) < 1e-5).all():
                    break
                jac = jacobian * weights[:, None]
                lhs = jac @ jac.transpose(0,2,1) + .008**2 * np.eye(6)
                update = (jac.transpose(0,2,1) @ np.linalg.solve(lhs, (error * weights)[...,None]))[...,0]
                update *= np.minimum(1, .12 / np.maximum(np.max(np.abs(update), axis=1), 1e-12))[:,None]
                pending = np.ones(len(guess), dtype=bool)
                previous = np.linalg.norm(error * weights, axis=1)
                for scale in (1, .5, .25, .125):
                    candidate = guess + scale * update
                    feasible = allowed(candidate) & pending
                    if not feasible.any():
                        continue
                    current_candidate, _ = fk(candidate[feasible])
                    improvement = np.linalg.norm(residual(target[feasible], current_candidate) * weights, axis=1) < previous[feasible]
                    chosen = np.flatnonzero(feasible)[improvement]
                    guess[chosen] = candidate[chosen]
                    pending[chosen] = False
                if pending.all():
                    break
            current, _ = fk(guess)
            errors.append(residual(target,current))
            positions.append(guess.copy())

        positions = np.array(positions).transpose(1,0,2)
        errors = np.array(errors).transpose(1,0,2)
        records = []
        for index in range(1):
            waypoints = positions[index]
            shifts = np.abs(np.diff(waypoints, axis=0))
            speed = np.deg2rad(limits[:, 2])
            accel = np.deg2rad(limits[:, 3])
            periods = np.maximum(1/15, np.maximum(np.max(1.875*shifts/speed,axis=1), np.max(np.sqrt((10*math.sqrt(3)/3)*shifts/accel),axis=1)))
            times = np.r_[0, np.cumsum(periods)]
            position_error = np.linalg.norm(errors[index,:,:3],axis=1)*1000
            rotation_error = np.rad2deg(np.linalg.norm(errors[index,:,3:],axis=1))
            # Exact quadratic coupled-boundary extrema on each straight segment.
            valid = True
            for start, end in zip(waypoints[:-1], waypoints[1:]):
                lo, hi = np.rad2deg(start), np.rad2deg(end)
                points = [0., 1.]
                if hi[5] != lo[5]:
                    crossing = -lo[5] / (hi[5] - lo[5])
                    if 0 < crossing < 1: points.append(crossing)
                for coeff in config[9:13]:
                    a,b,_ = coeff
                    den = 2*a*(hi[5]-lo[5])**2
                    if abs(den) > 1e-14:
                        vertex = ((hi[6]-lo[6])-2*a*lo[5]*(hi[5]-lo[5])-b*(hi[5]-lo[5]))/den
                        if 0 < vertex < 1: points.append(vertex)
                valid &= bool(allowed(np.array([start+t*(end-start) for t in points])).all())
            retarget_pass = bool(np.all(position_error<=1) and np.all(rotation_error<=1))
            records.append({"waypoints_rad":waypoints.tolist(),"time_s":times.tolist(),"segment_duration_s":periods.tolist(),"retarget_pass":retarget_pass,"continuous_nominal_position_pass":valid,"position_error_mm":position_error.tolist(),"rotation_error_deg":rotation_error.tolist(),"time_law":"quintic rest-to-rest"})
        return records[0]


def audit_direct(q_rad, actions):
    """Offline DROID interpretation in Tianji joint order, with no control output."""
    delta = 0.2 * np.clip(actions[:, :7], -1, 1)
    waypoints = np.vstack((q_rad, q_rad + np.cumsum(delta, axis=0)))
    degrees = np.rad2deg(waypoints)
    velocity = np.diff(degrees, axis=0) * 15
    acceleration = np.diff(velocity, axis=0) * 15
    def audit(steps):
        path = degrees[:steps + 1]
        samples = path[:-1, None] + np.diff(path, axis=0)[:, None] * np.linspace(0, 1, 101)[None, :, None]
        flat = samples.reshape(-1, 7)
        outside = (flat < limits[:, 0]) | (flat > limits[:, 1])
        return {
            "position_outside_axes": (np.flatnonzero(outside.any(axis=0)) + 1).tolist(),
            "position_or_coupling_violation": not bool(allowed(np.deg2rad(flat)).all()),
            "velocity_violation": bool((np.abs(velocity[:steps]) > limits[:, 2]).any()),
            "internal_acceleration_violation": bool((np.abs(acceleration[:steps - 1]) > limits[:, 3]).any()),
        }
    return {"waypoints_rad": waypoints.tolist(), "time_s": (np.arange(16) / 15).tolist(),
            "gripper_close_intent": (actions[:, 7] > 0.5).tolist(),
            "first_three": audit(3), "full_block": audit(15),
            "constraint_scope": "101 positions per joint segment; interval speeds and internal acceleration only"}


def retimed_ratios(candidate):
    shifts = np.abs(np.diff(np.rad2deg(candidate["waypoints_rad"]), axis=0))
    duration = np.diff(candidate["time_s"])[:, None]
    return {"peak_velocity_limit_ratio": float((1.875 * shifts / duration / limits[:, 2]).max()),
            "peak_acceleration_limit_ratio": float((10 * math.sqrt(3) / 3 * shifts / duration**2 / limits[:, 3]).max())}
