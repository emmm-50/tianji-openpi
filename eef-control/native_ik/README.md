# Offline right-hand IK

This line-oriented adapter calls the installed APEX `QpControllerCore` directly. It does not use ROS, network, or hardware. It uses the deployed `pro_m6s_696_new` kinematic model, 500 Hz step, collision pairs and velocity limits. Position limits come from the model. The VLA configuration keeps left hand and left elbow anchored, tracks `right_hand`, removes the unrequested right elbow orientation soft task, and sets `posture_cost=0`. Damping and the remaining core options retain their defaults. The Teleop installation is not modified.

For the current Tianji environment, build outside the source tree:

```sh
source /opt/ros/humble/setup.bash
cmake -S /home/nvidia/cph_dev/pi05/eef-control/native_ik -B /tmp/native-ik-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/native-ik-build -j1
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:$LD_LIBRARY_PATH
/tmp/native-ik-build/native_ik /home/nvidia/cph_dev/pi05/eef-control/native_ik/ik_tasks.yaml
```

This build links the installed core and the locally installed DAQP Python extension 0.8.5 plus libpython3.10. Its equivalence to the DAQP statically linked into the APEX node has not been established. Do not treat this offline adapter as a validated robot controller.

Send one JSON object per line on stdin; stdout returns one JSON object per request. Diagnostics go to stderr. First initialize with all 14 model-order joint positions in radians, left seven followed by right seven:

```json
{"type":"init","q":[0,-0.1,0,-0.1,0,0,0,-1.8452408314,-0.8560925722,1.5991649628,-1.8537635803,0.7187421918,0.1050546691,-0.3611849844]}
```

Subsequent steps use a world-frame `right_tool` target, metres and quaternion `xyzw`:

```json
{"type":"step","position":[0.5023625745,-0.3966023809,0.8469407004],"quaternion_xyzw":[-0.0059703669,0.0727962772,-0.0981977434,0.9924828764],"gripper_right":0.5}
```

Each successful step returns `ok`, seven absolute `jointcmd_right` radians and position/rotation residuals in metres/radians. A supplied finite `gripper_right` is copied unchanged; its units and valid range belong to the host integration. `ok` means the QP step succeeded, not that the target has been reached. Examine residuals for the application. Failed requests return `ok:false` and an error without a joint command. Init rejects out-of-range joint values instead of silently accepting core clamping. No target reachability, collision-free execution, hardware timing, or physical precision is implied by a successful step.

The solver advances one 2 ms step per request and keeps the previous solution; it does not synchronize live feedback automatically. Reinitialize with a complete measured state when starting a new run. Target interpolation and real control scheduling belong to the caller. Evidence for the posture/elbow comparison is in `evidence/base-eef-ik-20261119/ik-fix-comparison.json`.
