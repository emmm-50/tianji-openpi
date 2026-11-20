# Offline right-hand IK

This line-oriented adapter calls the installed APEX `QpControllerCore` directly. It does not use ROS, network, or hardware. CMake generates `marvin_95mm.xml` in the build directory from the shared URDF and the installed APEX collision geometry; the executable loads that generated scene. The solver retains its 500 Hz step, installed collision-pair configuration and velocity limits; position limits come from this MJCF. The VLA configuration keeps left hand and left elbow anchored, tracks `right_hand`, removes the unrequested right elbow orientation soft task, and sets `posture_cost=0`. Damping and the remaining core options retain their defaults. The system APEX/Teleop installation is not modified.

## Model source and coordinates

- Source: `robot_model/urdf/Pro-m6-696.urdf`; `robot_model` is a relative link to the shared Tianji resources. The generated MJCF uses this URDF; validation below used resource commit `47c51f0`.
- Arm joint origins, axes, limits, inertias, the 95 mm flange segments, and the fixed camera/gripper/tool structure follow that URDF. Meshes are read through the same link; there is no second mesh copy.
- The external IK continues to use the existing APEX world convention: `p_apex = Rz(+pi/2) p_urdf`, `R_apex = Rz(+pi/2) R_urdf`. This reconciles the model coordinate definitions; it is not a measured camera or robot calibration.
- The four finger prismatic joints are fixed at their URDF zero positions so the arm solver still has exactly 14 joints in left-seven/right-seven order. `gripper_right` remains an independent pass-through value; this adapter does not solve finger motion.
- The existing base and Link5 collision capsules and installed active collision pairs are retained. Added gripper geometry does not establish complete gripper collision checking.
- Source-model limitations are retained: `right_tool/left_tool` are nominal compatibility frames, with the source's 145 mm flange-to-tool offset, not measured grasp TCPs. The unusual right-finger origin in the source is not silently corrected.
- Joint2 now uses `[-2.0944, 2.0944]` and Joint4 `[-2.5307, 1.0472]` radians on both arms, matching the shared URDF instead of the old MJCF's `-0.1` upper limits. Previously recorded positive left Joint2 and near-zero left Joint4 can therefore initialize unchanged.

Build with CMake after changing the shared URDF or generator; the generated MJCF is loaded at process start. The installed APEX MJCF supplies the collision capsule recipe. Historical results using the system MJCF, old FK examples or hard-coded old limits must not be presented as tests of this model.

For the current Tianji environment, build outside the source tree:

```sh
source /opt/ros/humble/setup.bash
cmake -S /home/nvidia/cph_dev/pi05/eef-control/native_ik -B /tmp/native-ik-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/native-ik-build -j1
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:$LD_LIBRARY_PATH
/tmp/native-ik-build/native_ik /home/nvidia/cph_dev/pi05/eef-control/native_ik/ik_tasks.yaml
```

This build links the installed core and the locally installed DAQP Python extension 0.8.5 plus libpython3.10. Its equivalence to the DAQP statically linked into the APEX node has not been established. Do not treat this offline adapter as a validated robot controller.

Send one JSON object per line on stdin and read one JSON reply from stdout. Initialize with `{"type": "init", "q": measured_joints}`, replacing `measured_joints` with the 14 measured angles in radians (left seven, then right seven). Each `step` takes a world-frame `right_tool` position in metres and a quaternion in xyzw order. Diagnostics go to stderr.

Each successful step returns `ok`, seven absolute `jointcmd_right` radians and position/rotation residuals in metres/radians. A supplied finite `gripper_right` is copied unchanged; its units and valid range belong to the host integration. `ok` means the QP step succeeded, not that the target has been reached. Examine residuals for the application. Failed requests return `ok:false` and an error without a joint command. Init rejects out-of-range joint values. A rejected init discards the previous seed and the next step requires a successful init. No target reachability, collision-free execution, hardware timing, or physical precision is implied by a successful step.

The solver advances one 2 ms step per request and keeps the previous solution; it does not synchronize live feedback automatically. Reinitialize with a complete measured state when starting a new run. Target interpolation and real control scheduling belong to the caller. Evidence for the posture/elbow comparison is in `evidence/base-eef-ik-20261119/ik-fix-comparison.json`.

## Offline validation on 2026-11-20

The prior fixed-format scene passed comparison against the shared URDF (after the stated world-frame transform): 6 joint configurations, 35 link frames, maximum FK position error 3.6e-15 m and arm mass-matrix difference 1.6e-15. These are software consistency errors, not physical accuracy.

The original recorded 14-axis configuration initializes unchanged. Asking for its current FK pose leaves the right joint configuration unchanged to floating-point precision. A separate 1 mm target converged in 10 solver steps to 8.9e-8 m position residual and 7.2e-7 rad rotation residual. Out-of-range initialization still fails; gripper values still pass through unchanged. No hardware interface was used.

Results: `/home/nvidia/cph_dev/pi05/evidence/native-ik-model-20261120/validation.json`.

GR00T's older `check_ik_offline.py` and fixture refer to the installed system MJCF and old target, not this generated model.

The reproducible offline recording regression reads raw named joint feedback and computes each target independently from the shared URDF (with the world rotation described above):

```sh
source /opt/ros/humble/setup.bash
/usr/bin/python3 /home/nvidia/cph_dev/pi05/eef-control/native_ik/tests/replay_recorded.py /tmp/native-ik-build/native_ik
```

Set `TIANJI_FIXTURE_PROVENANCE` to your timestamp sidecar and `TIANJI_BAG` to the matching recording root containing `data/`. On Tianji the default sidecar is the adjacent `gr00t-tianji/recording/provenance.json`; its `bag` field supplies the default recording root. The test uses the video timestamps in that sidecar, emits the selected frame, bag timestamp and JointState header source timestamp (null if zero), residuals and joint differences, and fails on solver errors, residual thresholds or right-joint velocity-limit violations. After the initial hold, each subsequent frame target is applied for 33 or 34 solver steps on a cumulative 2 ms grid; the observed frame spacing is approximately 66.67 ms. This offline test uses the next sampled target over the preceding interval and is not a causal real-time replay. On 2026-11-20 the build-generated scene passed this regression; the largest frame-end errors were 1.45e-15 m and 9.52e-10 rad, and the maximum speed/limit ratio was 1.00000000000001. The largest difference from recorded right joints was 0.01430 rad; redundant IK need not reproduce the source joint configuration. This checks software consistency and continuity on that segment, not physical calibration.

The full 14-axis QP retains soft left-hand and left-elbow tasks and partial collision pairs involving both arms and the base. Only right-axis results are returned: the left tasks do not guarantee that the internal left configuration is fixed, nor do the configured collision geometries cover the complete robot. The installed APEX MJCF and shared URDF disagree on Joint2/4 limits; the shared URDF limits used here are not independently confirmed physical limits.

### Offline collision query acceleration

The adapter links against the installed QP core and the COAL 3.0.3 distance API. The link wrapper belongs to this offline executable. It uses world AABBs and mesh/capsule projection intervals to prove separation beyond the core's 150 mm detection distance. For close mesh-first OBBRSS/capsule queries it traverses the original BVH. An enclosing sphere gives a lower bound for a node, and a referenced triangle vertex gives an upper bound on the mesh distance. The traversal uses the original RSS bound wherever that comparison cannot rule out the node. COAL still computes triangle distances, nearest points and normals. Contact and unsupported queries use the installed implementation. A stationary pair can reuse a complete result when both poses and the request match. The QP retains all original tasks, speed limits, joint limits and collision pairs at each 2 ms integration step.

On 2026-11-21 the final build reproduced the previous binary's reported joints and residuals at every step of 12 slow targets and 32 earlier field targets (33 substeps per target), plus 20 seed perturbations spanning the threshold. For the 12 slow targets the median fell from roughly 794 ms to 22 ms. Of 305 individual near-field comparisons, five chose the adjacent triangle on the same shared edge. Witness points differed by at most 2.22e-16 m. The complete policy and measured Host mock results are in the companion GR00T worktree under `shadow_run/PERFORMANCE.zh-CN.md`.
