#!/usr/bin/python3
"""Read-only ROS state and graph monitor for the right-arm entry."""
import json
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import Int32, Int16MultiArray


class Watch(Node):
    def __init__(self, timing=False):
        super().__init__('apex_right_readonly_watch')
        self.mode = None
        self.robot = None
        self.robot_received = None
        self.mux = False
        self.graph_time = 0.
        self.mode_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                              durability=DurabilityPolicy.TRANSIENT_LOCAL)
        state_qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.mode_subscription = self.create_subscription(Int32, '/tj/control/input_mode', self.on_mode, self.mode_qos)
        self.mode_publishers = None
        self.create_subscription(Int16MultiArray, '/tj/info/robot_state', self.on_robot, state_qos)
        self.feedback = [] if timing else None
        self.feedback_received = None
        if timing:
            from marvin_msgs.msg import Jointfeedback
            self.create_subscription(Jointfeedback, '/tj/info/joint_feedback', self.on_feedback, state_qos)
        self.create_timer(.25, self.report)

    def on_mode(self, msg):
        self.mode = msg.data

    def on_robot(self, msg):
        self.robot = list(msg.data)
        self.robot_received = time.monotonic()

    def on_feedback(self, msg):
        now = time.monotonic()
        if self.feedback_received is not None and now - self.feedback_received < .02:
            return
        positions = list(msg.arm_positions[7:14])
        if len(positions) != 7:
            return
        self.feedback_received = now
        self.feedback.append({'stamp_sec': msg.header.stamp.sec, 'stamp_nanosec': msg.header.stamp.nanosec,
                              'received_monotonic_s': now, 'right_joint_rad': positions})

    def report(self):
        now = time.monotonic()
        if now - self.graph_time >= 1:
            publishers = self.get_publishers_info_by_topic('/tj/control/input_mode')
            gids = tuple(sorted(bytes(p.endpoint_gid) for p in publishers))
            if gids != self.mode_publishers:
                self.mode_publishers = gids
                self.mode = None
                self.destroy_subscription(self.mode_subscription)
                self.mode_subscription = self.create_subscription(Int32, '/tj/control/input_mode', self.on_mode, self.mode_qos)
            subscribers = self.get_subscriptions_info_by_topic('/tj/control/user/joint_cmd_B')
            self.mux = (len(publishers) == 1 and publishers[0].node_namespace == '/tj'
                        and publishers[0].node_name in ('joint_mux_node', 'joint_cmd_mux')
                        and any(x.node_namespace == publishers[0].node_namespace and x.node_name == publishers[0].node_name
                                for x in subscribers))
            self.graph_time = now
        data = {'monotonic': now, 'mode': self.mode,
                'robot': self.robot, 'robot_received': self.robot_received, 'mux': self.mux}
        if self.feedback is not None:
            data['joint_feedback'] = self.feedback
            self.feedback = []
        print(json.dumps(data), flush=True)


def main():
    rclpy.init()
    node = Watch(timing='--timing' in sys.argv[1:])
    try:
        rclpy.spin(node)
    except ExternalShutdownException:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
