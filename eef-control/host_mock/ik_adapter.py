"""Offline native IK adapter. Produces candidates only; never opens a robot connection."""
import json
import subprocess

from host_mock import action_from_ik

DT_NS = 2_000_000


class NativeSolver:
    def __init__(self, binary, config):
        self.process = subprocess.Popen(
            [binary, config], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def __call__(self, request):
        self.process.stdin.write(json.dumps(request, allow_nan=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("native IK terminated")
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        self.process.wait()
        self.process.stdout.close()


class IKAdapter:
    def __init__(self, solve):
        self.solve = solve
        self.plan_ns = None

    def initialize(self, snapshot, *, feedback_source_ns, feedback_received_ns, plan_start_ns):
        self.plan_ns = None
        reply = self.solve({"type": "init", "q": snapshot["joint_states"]["positions"]})
        if not reply.get("ok"):
            raise ValueError(f"IK init failed: {reply}")
        self.feedback = {
            "source_ns": feedback_source_ns,
            "snapshot_stamp_ns": snapshot.get("stamp"),
            "received_ns": feedback_received_ns,
        }
        self.plan_ns = plan_start_ns

    def step(self, target, *, observation_id, observation_time_ns, target_time_ns,
             stop_requested=None):
        """Return None on caller cancellation. The next target then needs a fresh init."""
        if self.plan_ns is None:
            raise ValueError("initialize from feedback first")
        steps = (target_time_ns - self.plan_ns) // DT_NS
        if steps < 1:
            raise ValueError("target must advance at least one solver step")
        if "type" in target:
            raise ValueError("target must not include type")
        plan_ns = self.plan_ns
        self.plan_ns = None
        for _ in range(steps):
            if stop_requested is not None and stop_requested():
                return None
            reply = self.solve({"type": "step", **target})
            if not reply.get("ok"):
                raise ValueError(f"IK step failed: {reply}")
        action = action_from_ik(reply)
        self.plan_ns = plan_ns + steps * DT_NS
        return {
            "observation_id": observation_id,
            "observation_time_ns": observation_time_ns,
            "target_time_ns": target_time_ns,
            "plan_time_ns": self.plan_ns,
            "steps": steps,
            "feedback": self.feedback,
            "ik": reply,
            "action": action,
        }
