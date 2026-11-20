#!/usr/bin/env python3
"""Exercise installed VLAHost WebSocket handler in-process with fake ROS only."""
import asyncio
import importlib.util
import json
import math
import pathlib
import sys
import threading
import time
import types

HOST = pathlib.Path("/opt/kernelmind/apex/install/vlahost/lib/python3.10/site-packages/vlahost/server.py")


def load_host():
    # Insert inert ROS/message modules before importing server.py. Node construction,
    # FastAPI startup, ROS initialization and external sockets are never invoked.
    saved = {}
    def module(name, **attrs):
        if name not in saved:
            saved[name] = sys.modules.get(name)
        obj = types.ModuleType(name)
        obj.__dict__.update(attrs)
        sys.modules[name] = obj
        return obj
    class Node:
        pass
    class Message:
        def __init__(self):
            self.header = types.SimpleNamespace(stamp=None)
            self.positions = []
            self.data = 0.0
    for package, names in {
        "geometry_msgs": ["PoseStamped"], "marvin_msgs": ["IKRequest", "JointcmdArm", "Jointfeedback"],
        "sensor_msgs": ["CompressedImage"], "std_msgs": ["Float32", "Float32MultiArray", "Int32MultiArray"],
    }.items():
        parent = module(package)
        parent.msg = module(package + ".msg", **{name: type(name, (Message,), {}) for name in names})
    sys.modules["marvin_msgs"].srv = module("marvin_msgs.srv", Int=type("Int", (), {}), JsonCommand=type("JsonCommand", (), {}))
    rclpy = module("rclpy")
    rclpy.executors = module("rclpy.executors", ExternalShutdownException=type("ExternalShutdownException", (Exception,), {}))
    rclpy.node = module("rclpy.node", Node=Node)
    rclpy.qos = module("rclpy.qos", qos_profile_sensor_data=object())
    spec = importlib.util.spec_from_file_location("isolated_installed_vlahost", HOST)
    host = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(host)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return host


class Publisher:
    def __init__(self, on_publish=None):
        self.messages = []
        self.on_publish = on_publish
    def publish(self, message):
        if self.on_publish is not None:
            self.on_publish(time.monotonic_ns())
        self.messages.append(message)


async def call_asgi(host, payload):
    scope = {"type": "websocket", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "scheme": "ws", "path": "/ws/action", "raw_path": b"/ws/action",
             "query_string": b"ack=true", "headers": [], "client": ("mock", 0),
             "server": ("mock", 0), "root_path": "", "subprotocols": []}
    events = iter([{"type": "websocket.connect"},
                   {"type": "websocket.receive", "text": json.dumps(payload)},
                   {"type": "websocket.disconnect", "code": 1000}])
    sent = []
    async def receive():
        return next(events)
    async def send(event):
        sent.append(event)
    await host.app(scope, receive, send)
    return sent


def run_action(payload, *, host=None, loop=None, on_right_publish=None):
    host = load_host() if host is None else host
    node = host.VlaHostNode.__new__(host.VlaHostNode)
    node._action_lock = threading.Lock()
    node._control_mode = "joint"
    node.eef_mode_enabled = True
    node.intervention_status = lambda: {"active": False, "transitioning": False}
    node.get_clock = lambda: types.SimpleNamespace(now=lambda: types.SimpleNamespace(to_msg=lambda: "fake_stamp"))
    node.joint_cmd_pub_L, node.joint_cmd_pub_R = Publisher(), Publisher(on_right_publish)
    node.eef_ik_request_pub = Publisher()
    node.gripper_controller_pub_L, node.gripper_controller_pub_R = Publisher(), Publisher()
    host.vla_node = node
    call = call_asgi(host, payload)
    events = asyncio.run(call) if loop is None else loop.run_until_complete(call)
    return {"accepted": any(e["type"] == "websocket.accept" for e in events),
            "ack": [json.loads(e["text"]) for e in events if e["type"] == "websocket.send"],
            "ik_requests": len(node.eef_ik_request_pub.messages),
            "joint_left": [m.positions for m in node.joint_cmd_pub_L.messages],
            "joint_right": [m.positions for m in node.joint_cmd_pub_R.messages],
            "gripper_left": [m.data for m in node.gripper_controller_pub_L.messages],
            "gripper_right": [m.data for m in node.gripper_controller_pub_R.messages]}


def action_from_ik(result):
    if result.get("ok") is not True:
        raise ValueError("IK result is not successful")
    action = {"control_mode": "joint", "jointcmd_right": result["jointcmd_right"]}
    if "gripper_right" in result:
        gripper = float(result["gripper_right"])
        if not math.isfinite(gripper):
            raise ValueError("gripper_right must be finite")
        action["gripper_right"] = gripper
    return action


if __name__ == "__main__":
    # Read one successful IK JSON response on stdin; do not forward diagnostics.
    action = action_from_ik(json.load(sys.stdin))
    print(json.dumps(run_action(action), allow_nan=False))
