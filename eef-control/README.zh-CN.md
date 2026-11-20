# 右臂末端目标 → IK → VLAHOST 关节消息

给定已对齐到 APEX `world` 的 `right_tool` 绝对位姿和实测双臂关节，这个入口生成 VLAHOST 待发的右臂七轴绝对角。录像回归从原始 ROS 反馈取值，以共享 URDF 独立计算目标。消息测试使用天玑安装版 Host 路由和内存接收端。π₀.₅ Base 与 1500 关节路线的历史交接见[接力说明](HANDOFF.zh-CN.md)。

## 为什么真实反馈现在能初始化

录像中的部分左臂关节位置超出旧系统 MJCF 的模型上限。共享 95 mm URDF 与安装版左右臂 URDF 的 14 个关节原点、轴和限位一致。

构建从共享 `tianji-robot-resources` 的 95 mm URDF 生成 QP 所需的 MJCF，验收使用资源提交 `47c51f0`。录像按 `Joint1_L…Joint7_L, Joint1_R…Joint7_R` 名称取角，现场 `/tj/info/joint_feedback` 的 `Jointfeedback.arm_positions` 也按此顺序排列。厂商参考源码 `marvin_ros2_control_wb/src/marvin_robot.cpp` 的 `ReadState` 从 SDK 的 A、B 臂读取关节角，分别乘 `D2R`，依次写进 ROS 向量。此处直接用 ROS 的 rad 值。实物零位与机械止挡仍需独立核实。

右臂位姿使用固定基座，但原 QP 同时处理左手、左肘软任务和双臂碰撞对，因此初始化仍使用实测 14 轴。模型保留两侧 Link4/5 对底座及彼此的碰撞检查。内部左臂允许变化，只发送右七轴时的物理路径和夹爪碰撞间隙尚未验收。

## 接入契约

| 输入或输出 | 约定 |
| --- | --- |
| 当前反馈 | Host 快照中的 `joint_states.positions` 或由同一条 ROS 反馈组成的等价 14 轴数组。Host 顶层 `stamp` 是生成快照的时间；完整 ROS 消息另有源 `header.stamp`。本地接收时间单独记录。 |
| 动作目标 | 模型 world 系的 `right_tool` 绝对 xyz（米）与 xyzw 四元数。URDF world 到 APEX world 的模型定义为左乘 `Rz(+π/2)`。`right_tool` 是名义工具点；DROID 的基座、工具轴和实物抓取点需在上游完成对齐。 |
| 求解时间 | 一次 `init` 固定规划起点，同一动作块沿用求解状态。每个目标在自己的区间内保持，按累计 2 ms 栅格积分；返回最后一个已完成步的规划时间和位姿残差。规划与目标时间使用同一时钟；在线收到新观测时由调用方决定何时用新反馈重置。 |
| 待发消息 | 仅向外传 `action`，即 `{"control_mode":"joint","jointcmd_right":[…]}`。数值按右 J1…J7 排列，单位 rad。夹爪完成单位和开闭映射后可另带 `gripper_right`，由 Host 单独发布。 |
| 控制通道 | 安装版 `/ws/action?ack=true` 在 joint 模式对每条有效消息发布一次 `JointcmdArm.positions`。`/tj/control/user/joint_cmd_B` 经输入源 3 的 mux 到 `/tj/control/joint_cmd_B`。外置 IK 使用一个关节发送源，Host 配置 `eef_mode_enabled=false`。夹爪经 `/tj/control/gripperValueR` 独立发布。 |

`ik_adapter.py` 可由 Python 调用。将本目录的 `host_mock` 加入 `PYTHONPATH`，传入已构建的二进制和任务配置。下面按 GR00T 适配器返回的 `nominal_offset_s` 作为动作区间起点，每个样本占一段；首个样本的偏移是 0，首段结束时才取待发结果。此例假定动作块按 15 Hz 采样，规划时刻仅供调用方排程。

```python
from ik_adapter import IKAdapter, NativeSolver

solver = NativeSolver(binary, ik_tasks_yaml)
try:
    planner = IKAdapter(solver)
    planner.initialize(snapshot, feedback_source_ns=joint_header_ns,
                       feedback_received_ns=received_ns, plan_start_ns=observation_ns)
    for sample in aligned_targets:
        end_ns = observation_ns + round((sample["nominal_offset_s"] + 1 / 15) * 1e9)
        result = planner.step(
            {"position": sample["position_m"], "quaternion_xyzw": sample["quaternion_xyzw"]},
            observation_id=frame_id, observation_time_ns=observation_ns, target_time_ns=end_ns)
        candidate = result["action"]
finally:
    solver.close()
```

此入口计算每段末端的关节消息。QP 成功仅表示完成数值迭代，调用方可从 `result["ik"]` 读取位置和姿态残差。Host 收到消息后立即发布；它的 ACK 表示处理结果，干预时可能返回 `suppressed`。Robot 安装配置的控制循环为 200 Hz，`joint_states` 配置为 100 Hz。500 Hz 是 IK 积分频率。真实发送节拍、反馈延迟及路径跟踪需要单独验证。

## 天玑复跑

```bash
cd /home/nvidia/cph_dev/pi05/eef-control
source /etc/apex/apex_ros_env.sh
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
export PYTHONDONTWRITEBYTECODE=1
cmake -S native_ik -B /tmp/gr00t-eef-module-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/gr00t-eef-module-build -j2
/usr/bin/python3 native_ik/tests/replay_recorded.py /tmp/gr00t-eef-module-build/native_ik
/usr/bin/python3 host_mock/test_host_mock.py
/usr/bin/python3 host_mock/test_ik_host.py /tmp/gr00t-eef-module-build/native_ik "$PWD/native_ik/ik_tasks.yaml"
```

录像回归取第 300、302…330 帧之前最近的 `/tj/joint_states`。求解起点取第 300 帧原值，其余帧以各自的共享 URDF FK 作为已知目标。测试记录每帧位置/姿态误差、每个 2 ms 步的右轴变化与限速，覆盖初始保持和运动片段。录像中下一帧的 FK 用于前一个规划区间，属于离线有真值的回放。

第 300 帧同一条未改动的反馈，旧版二进制返回 `initial joint outside model limits`，新版成功。16 帧共运行 500 个内部步，最大帧末位置残差为 1.45e−15 m，姿态残差为 9.52e−10 rad。相邻帧 300/302 的 FK 也经过 GR00T `ik_targets` 解码及上方 Python 调用，模拟 Host 收到两条右七轴消息。该对接检查使用了已知的测试坐标变换。

现场只读反馈也通过了初始化和保持目标的模拟接收。位姿反馈来自模型计算，物理 TCP 精度仍需独立测量。[原生 IK](native_ik/README.md) · [Host mock](host_mock/README.md)

## 早期 π₀.₅ 轨迹的 IK 稳态误差对照

原通用任务配置同时跟踪右手位姿、保持初始关节姿态，并保持初始右肘方向。在这条录制轨迹中，后两项软目标与右手目标竞争，导致终点保持后仍有偏差。相同轨迹、初始状态与 1 秒保持时间的对照结果如下：

| 配置 | 保持后位置误差 | 保持后姿态误差 |
| --- | ---: | ---: |
| 原默认配置 | 8.079 mm | 0.04552 rad |
| 仅取消关节姿态保持代价 | 3.131 mm | 0.02689 rad |
| 仅取消右肘方向软任务 | 5.928 mm | 0.02730 rad |
| 同时取消这两项软目标 | 数值精度附近 | 约 3.36e-10 rad |

修复只作用于 `native_ik/` 中的 VLA 专用适配器：`posture_cost=0`，任务配置不包含右肘方向目标。左手、左肘任务、速度阻尼及模型关节限位、速度和碰撞配置继续保留。未修改 APEX 安装或已有遥操配置。

这证明本段模型轨迹上的稳态偏差得到解决，不代表真实机械臂精度或所有目标可达。完整对照保存在 `evidence/base-eef-ik-20261119/ik-fix-comparison.json`。

## 虚拟 SDK 联调

[virtual_sdk](virtual_sdk/README.md) 使用已保存的真实 base `world_eef` 50×32 原始数组，通过人造的小范围位置、旋转和夹爪映射生成测试目标，再运行现有 IK、真实 Host ASGI 处理和内存 FakeSDK。SDK 的输入来自 Host 假发布器捕获值，不旁路 Host；每帧检查关节及夹爪回读，非法输入不得改变 SDK 状态或写入次数。

这验证软件接口传值，不需要真实机械臂或启动真实 ROS 节点。50 帧是保存输出的开环回放，50 次独立 ASGI 调用，不是新观测驱动的策略闭环，也不覆盖真实网络连接。人造映射的通道、尺度和参考系仅供虚拟测试，不能用作原始 base 的已验证末端动作解码器。
