# 2026-11-20 下午接力：π₀.₅ Base 末端路线与 1500 关节路线

主要工作区：天玑 `/home/nvidia/cph_dev/pi05`。电脑连接：`ssh TianJi-Codex-wired`。

本次按两条路线交接，不增加 FK 转换：

| 路线 | 当前状态 | 接力入口 |
| --- | --- | --- |
| 原始 `pi05_base` → 原生末端目标 → IK → VLA Host → Robot | 原始权重推理已通过；IK 与 Host 处理已分别验证。Base 的末端通道、姿态表示、参考系和反归一化仍待对齐，尚无完整原生末端真机桥 | `eef-control/base_probe/run.py`、`eef-control/native_ik/` 和下述 Host 协议 |
| 新训练 `base30k-b32/1500` → 关节目标 → VLA Host → Robot | 1500 已离线评估并成功恢复；已增加 `--policy base1500` 加载选项。使用现有关节客户端，不经过 IK | `tianji-lora/apex_right_live.py --policy base1500` |

本交接面向现场同学直接接入真机，不以虚拟回放作为操作步骤。此前 `virtual_sdk/` 使用人工测试映射，只保留为开发测试历史，不属于 Base 的原生末端解码。

## 1. 先看文件与现场资产

| 内容 | 天玑路径 |
| --- | --- |
| 原始 Base | `weights/pi05_base/params` |
| 1500 checkpoint | `cache/tianji-lora/right-orange-20261117-162906/checkpoints/pi05_tianji_right_lora/base30k-b32/1500` |
| 1500 自带统计 | 上述 checkpoint 的 `assets/tianji/right_orange/norm_stats.json` |
| OpenPI 子模块 | `openpi/`，本次固定提交 `215abfb217dbac7d5f1273282331b9b1866c0479` |
| Base 采样 Python | `envs/openpi-sm87/bin/python` |
| 1500 客户端环境入口 | `cache/tianji-lora/right-orange-20261117-162906/runtime.sh` |
| 1500 本地配置辅助模块 | 同一工作目录中的 `right_lora.py`；由现有环境入口加载 |
| 现有关节规划依赖 | `/home/nvidia/wsb_ws/tools/review_model_compatibility.py`、安装版 `ccs_m6s_696.MvKDCfg`、`offline-replay/reference/droid-panda-33ae6a6.xml` |
| IK、Host 和 SDK 开发结果 | `eef-control/` |
| 本次证据 | `evidence/base-eef-ik-20261119/`、`evidence/handoff-20261120/` |

Git 保存源码与说明。权重、Conda 环境、相机观测、checkpoint、现场证据和 `/opt/kernelmind/apex` 安装留在天玑；新克隆的仓库不等于一份完整机器环境。现有工作区还有其他工作未提交，接力直接使用上述目录即可。

截至本次交接前的只读快照：未见活动训练或评估主进程，较早评估批次在 10:46 完成；可用内存约 37 GiB。1500 是最新确认完整的保存点，训练日志之后到过 1509，未见这 9 步另存。两个旧数据 worker 仍在，本轮未处理。现场状态可能随其他同学操作改变。

## 2. 真实 Host 与 Robot 启动

以下是下午现场使用的现成操作命令。本轮代码整理没有执行这些控制操作。

已有 Robot、Teleop、Tool、mux 和可用 Host 沿用现场实例，下面的命令供对应模块缺失时启动；相机也沿用已有实例。

终端一启动现有模块：

```bash
source /etc/apex/apex_ros_env.sh
sudo systemctl start apex-robot.service
sudo systemctl start apex-tool.service
sudo systemctl start apex-teleop.service
```

相机未运行时，沿用现有四宫格入口：

```bash
source /etc/apex/apex_ros_env.sh
cd /home/nvidia/webrtc
ros2 launch gmsl_quadcam quad_csi_quickview.launch.py
```

终端二启动 VLA Host，显式指定 `/tj` namespace：

```bash
source /etc/apex/apex_ros_env.sh
host_bin="$(ros2 pkg prefix vlahost)/lib/vlahost/vlahost_server"
"$host_bin" --host 127.0.0.1 --port 8000 --ros-args \
  -r __ns:=/tj \
  -p joint_states_topic:=info/joint_feedback \
  -p eef_left_topic:=info/eef_left \
  -p eef_right_topic:=info/eef_right \
  -p eef_mode_enabled:=false
```

安装版 launch 虽声明 `ros_namespace`，但没有传给 Node，因此这里使用显式 ROS remap。`eef_mode_enabled=false` 对应本交接的外置 IK → 关节消息路线，不再调用 Host 内部 IK。

现场通过 APEX UI 或现有脚本设置 Robot 与输入源。首次连接、Robot 状态为 `[-1,-1]` 时，用现有操作准备并申请 Ready：

```bash
cd /home/nvidia/cph_dev/pi05
bash tianji-lora/apex_right_control.sh prepare
bash tianji-lora/apex_right_control.sh ready
```

设置位置模式和 VLA 输入源：

```bash
bash tianji-lora/apex_right_control.sh position
bash tianji-lora/apex_right_control.sh vla
```

Robot 已处于 `[1,1]` 时可直接选择 `vla`，不用重复 Ready/Position。

参数含义：Robot `mode=1` 是位置模式；mux `input=3` 是 user/VLA 输入。二者不是同一个参数。上述脚本是现场已有实现，本轮没有增加控制限制或审批步骤。

查看接口：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/state
```

## 3. 1500：直接跑原生关节输出

在天玑另一个终端执行：

```bash
cd /home/nvidia/cph_dev/pi05
bash cache/tianji-lora/right-orange-20261117-162906/runtime.sh \
  tianji-lora/apex_right_live.py \
  --policy base1500 --segments 0 --num-steps 10 --gripper
```

`--segments 0` 为持续运行，`--segments 1` 为一段；`--timing` 打印时序。`Ctrl+C` 退出推理客户端。结束当前 VLA 路由使用现有命令：

```bash
bash tianji-lora/apex_right_control.sh release
```

`release` 只切换关节 mux 到 0；夹爪独立发布，客户端退出也不表示撤销旧目标。现场急停沿用已有按键。

本次新增的 `base1500` 使用 `right_lora.make_config('base30k-b32')` 与 checkpoint `1500`，归一化从 checkpoint 自带资产加载。它不是之前的 `lora3750`。

现有客户端输入为四宫格右上 `tr`（右眼）、右下 `br`（右腕），状态为右臂七轴 rad 和夹爪反馈，任务文本为 `pick the orange and place it on the black mouse pad`。模型产生 50×8 动作块，七轴为绝对关节目标；现客户端每段选择第 6 帧（index 5），沿用现有插值、发送及夹爪逻辑。此路线不做末端解码，也不加 FK/IK。

本轮验证了选择项、checkpoint、统计路径和参数传递；1500 此前已完成离线评估。新增选项没有在本轮实际驱动机器人。

## 4. 原始 Base：原生末端路线的接力点

### 4.1 已可运行的原始输出入口

```bash
cd /home/nvidia/cph_dev/pi05
base_out=$(mktemp -d /tmp/pi05-base-output.XXXXXX)
LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu/nvidia \
XLA_FLAGS=--xla_gpu_autotune_level=4 XLA_PYTHON_CLIENT_PREALLOCATE=false \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
envs/openpi-sm87/bin/python -u eef-control/base_probe/run.py --output-dir "$base_out"
```

它读取历史录制观测，恢复原始 Base 权重，输出 `base-probe.json` 与 `base-probe.npz`。NPZ 中的 `plain`、`world_eef`、`wrist_eef` 均为 50×32 原始归一化数值；三个提示使用同一观测、同一噪声。需要保存本轮数据时将这两个文件复制到自己的结果目录，之后清理 `$base_out`。

本入口的 DROID 输入包装与状态统计属于当前探索配置。末端提示前缀来自 π₀ 的公开讨论，并未据此确认 π₀.₅ 的动作模式。整理后的入口已做真实 GPU 回归，三组输出均有限；结果见 `evidence/handoff-20261120/base-probe/`。

### 4.2 待补的解码接口

接力同学需要把与该 Base checkpoint 匹配的动作定义接成：

```text
decode_base_action(raw_action, observation)
    → position: [x, y, z]                 # m，模型 world 坐标
    → quaternion_xyzw: [qx, qy, qz, qw]  # right_tool 的朝向
    → gripper_right: value               # 与现场夹爪接口对应
```

目前未对齐的技术项是：动作通道顺序、反归一化统计、姿态编码、参考坐标系、绝对/增量方式和夹爪映射。Base 前缀改变了原始输出，但不单独证明这些语义。现有 `base_probe` 没有这层解码器；1500 的关节统计也不是这层的末端统计。

解码完成后，对齐 IK 模型中的 `world → right_tool`；这与另一个 MIOS 工具的 `Base_R → flange_R` 不是相同的帧名称。模型和输入帧说明见 [native_ik](native_ik/README.md)。

### 4.3 IK 编译与调用

```bash
source /opt/ros/humble/setup.bash
cmake -S /home/nvidia/cph_dev/pi05/eef-control/native_ik \
  -B /tmp/pi05-native-ik-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/pi05-native-ik-build -j1
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
/tmp/pi05-native-ik-build/native_ik \
  /home/nvidia/cph_dev/pi05/eef-control/native_ik/ik_tasks.yaml
```

IK 是 stdin/stdout 每行一个 JSON 的常驻求解进程。先用 Host `/state` 的 `joint_states.positions` 初始化左右共 14 轴（左 7、右 7，rad）：

```text
{"type":"init","q":[左臂7轴,右臂7轴]}
{"type":"step","position":[x,y,z],"quaternion_xyzw":[qx,qy,qz,qw],"gripper_right":g}
```

每条 `step` 推进 2 ms 的内部求解步，沿用上一解；成功响应含 `jointcmd_right`、残差及可选夹爪。模型推理、动作块时间解释和发送节拍由调用方安排，不能把 50 帧维度当作已经确定的控制频率。此进程没有实时状态订阅；新一轮控制起点通过 `init` 明确给入反馈。

本次修复的是 VLA 专用软目标：取消初始关节姿态代价和未请求的右肘方向目标，原生模型与其余配置保留。同一 5 秒轨迹的稳态残差由 8.08 mm 降到数值精度附近，运动末点误差约 0.027 mm。它是模型内结果，不是实机 TCP 精度。

## 5. IK 输出接真实 VLA Host

连接：`ws://127.0.0.1:8000/ws/action?ack=true`。从 IK 成功响应中取关节和夹爪字段，发送：

```json
{"control_mode":"joint","jointcmd_right":[0.1,-0.2,0.3,-0.4,0.5,-0.6,0.7],"gripper_right":0.5}
```

上述数值只示意格式。`jointcmd_right` 是右臂七个绝对关节角，单位 rad；夹爪单独发布。Host 到 Robot 的路径为：

```text
/ws/action → /tj/control/user/joint_cmd_B
           → joint_cmd_mux（input=3）
           → /tj/control/joint_cmd_B
           → Robot / SDK
```

夹爪路径是 `/tj/control/gripperValueR`，不经过关节 mux。Host 每收到关节帧发布一次，没有替调用方插值；Robot 安装配置为 200 Hz。现有 1500 客户端是 50 Hz 逐条 ACK 发送，Base 外置 IK 的调度需要在新接入中明确实现。ACK `success` 表示 Host 处理；`suppressed` 表示当前输入被干预逻辑抑制。

可复用的源码位置：

- `tianji-lora/apex_right_dry_run.py`：图像切分、观测包装与模型选择。
- `tianji-lora/apex_right_live.py`：`ObservationStreams`、`send_points` 和现有关节执行路径。
- `/opt/kernelmind/apex/install/vlahost/lib/python3.10/site-packages/vlahost/server.py`：真实 Host 接口实现。
- `eef-control/native_ik/`：本轮外置 IK。

本轮没有把 Base 原生末端解码和真实发送循环拼成单一运行器。交接的明确分工是：1500 用现成关节入口；Base 原生末端路线从上面的解码接口继续接，不使用历史人造映射替代。

## 6. 验证记录与 Git 范围

- `evidence/base-eef-ik-20261119/ik-fix-comparison.json`：稳态误差四组对照。
- `evidence/base-eef-ik-20261119/ik-host-completion.json`：IK、Host 处理验证汇总。
- `evidence/base-eef-ik-20261119/base-actual-20261120.json/.npz`：第一次 Base 真实采样。
- `evidence/handoff-20261120/base-probe/`：本次持久入口回归。

既有 Host/假 SDK 测试证明过软件字段传递，但不作为本交接的现场流程。此次整理未启动真实 Host/Robot/Teleop、未切模式、未发机械臂或夹爪动作，未重启训练。可复跑源码和文档保留；一次性测试和构建目录用完清理。
