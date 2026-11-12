# 天玑观测与动作契约：只读调查

调查日期 2026-11-06。范围：天玑 `/home/nvidia/cph_dev` 中指定项目、安装 SDK 头文件和静态资料；没有连接设备、启动 ROS/SDK/策略服务或采样。下文“参考源码”是资料目录中的源码，不证明当前正在运行该版本；“历史记录”不代表当前状态；“安装声明”不证明固件行为。硬件未在本次验证。

## 结论

现有资料不足以构造可信的天玑同步观测—动作回放。限定目录 `pi05`、`tianji_quest_nova`、`mios_marvin`、`robot_resources/tianji` 递归查找 `.mcap`、`.db3`、`.bag`、`.hdf5`、`.h5`、`.parquet` 和 `metadata.yaml` 未找到文件；这仅是所列目录和格式的查找结果，不排除其他位置或格式。仓库中的视频不能因此认作带动作、状态与同步时间的示教。既有 pi05 验收使用合成数据，不是天玑采样（[部署记录](../README.zh-CN.md) 的离线验证章节）。

### 右夹爪当前只读入口补充（2026-11-12）

已复用现有 /tj/info/gripper_feedback_R 取得真实ROS反馈，左右接口结构对称；字段、发布者、原始CAN只接收证据和未切模式的范围见 [右夹爪只读调查](RIGHT_GRIPPER_READONLY.zh-CN.md)。驱动_R_err=[1]为电机上报On。机械臂模式话题目前被ready条件替换为[-1,-1]，不能据此证明当前mode3或要求切mode0；旧工具限制与SDK接口能力分开。该更新补充下文历史静态调查，不把ROS发布频率当CAN新鲜度或归一化开口。

### 用户补充目录后的更新（2026-11-06）

已只读检查 /home/nvidia/Tianji/resources/{handeye_calibration,camera_projects} 及 ~/.ros/log。现已找到 D435 单图与七轴状态的真实静止历史样本、四台SH5逐台内参、D435候选手眼外参，以及没有图像的历史MCAP状态包。因此“未发现文件”仅指上文原限定目录，不能理解为整机没有真实样本。仍未取得完整的双视角、七轴、真实夹爪反馈和任务文本的同步输入。

用户已选首轮右侧。代表样本核对、优先复用APEX录制的方案和分项设备授权见 [右侧最小真实样本方案](REAL_SAMPLE_PLAN.zh-CN.md)，证据见 [real-sample-review.json](../offline-replay/evidence/real-sample-review.json)。本轮只做离线核对，没有现场ROS图、设备采样或模型重跑。

### 常用格式候选补查

[只读文件检查] 在上述四个项目目录内进一步查找 `.npz`、`.npy`、`.jsonl`、`.csv`、`.mp4`，排除环境、权重、Git、build、缓存、第三方源码与材料目录。候选仅有 `/home/nvidia/cph_dev/pi05/offline-replay/evidence/synthetic.npz` 和 `synthetic-result/{actions,droid_example_clipped}.npy`。前者字段含两张 224×224×3 uint8 图、七维关节、一维夹爪、文本与 metadata；但 [回放说明](../offline-replay/README.zh-CN.md) 的合成样本生成方法 明确 seed 0 随机生成、无设备和空时间戳，不能作为真实同步观测。两个 NPY 均为 15×8 模型输出，不是设备动作记录。`tianji_quest_nova` 全目录额外查找上述五种格式也未见候选。检索有明确目录、扩展名和排除范围，不排除其他路径、格式或尚未发现的记录。

### 模型侧

- [固定上游源码] `/home/nvidia/cph_dev/pi05/openpi/src/openpi/policies/droid_policy.py:10-17,35-50,77-81`：输入外部图、腕部图、7 关节位置和 1 夹爪位置、任务文本；state 拼为 8 维，PI05 的第三图像槽置零且 mask 为 false；输出前 8 维。图像示例是随机 224×224×3 uint8，非设备数据。
- [固定上游源码] `/home/nvidia/cph_dev/pi05/openpi/src/openpi/training/config.py:630-640` 配置 `pi05_droid` horizon 15；`examples/droid/main.py:22-23,79-80,119-126,132-155` 示例声明 15 Hz、关节速度和夹爪位置，夹爪按 0.5 二值化，旧示例却断言 10×8。实际本机离线验收是 15×8（[交接记录](../HANDOFF.zh-CN.md) 的上阶段环境事实）；旧断言不能直接用于当前配置。速度的具体缩放、方向、夹爪物理意义不能仅凭上述示例推定为天玑等价接口。

### 三条证据路径的边界

- [已安装 100343014 SDK 声明] `/usr/local/include/marvinsdk/MarvinSDK.h:52,185-187` 声明状态读取和两侧位置命令；`:364-365` 的 `SetJointPostionCmd` 明确 A/B 七关节目标角度单位为度；`/home/nvidia/cph_dev/mios_marvin/docs/MARVIN_CONTROL_REFERENCE.zh-CN.md:9-13,37-51` 记录已安装版本及 MIOS 适配仍未实现。这些声明不证明有活动控制会话或当前设备效果。
- [APEX 历史运行链] `/home/nvidia/cph_dev/tianji_quest_nova/provenance/interface_audit.zh-CN.md:9,15-24` 记录 Teleop → QP/仲裁 → Robot Node/SDK 和 ApexTool → CAN，以及历史图；原生执行文件与随包 Python 不可直接视为同一实现。该证据不是本次活动进程检查。
- [旧 MoveIt/ROS 参考源码] 下列 `marvin_pro_20261015/ros_source` 是静态参考，不证明是当前 APEX 部署、当前活动控制链或其 SDK 版本。

### 天玑侧别、状态与命令

- [参考源码] `/home/nvidia/cph_dev/robot_resources/tianji/research/marvin_pro_20261015/ros_source/src/marvin_real_control/src/marvin_real_control/trajectory_to_marvin_cmd.py:21-24,83-109` 将 A 与左侧 `Joint1_L` 至 `Joint7_L`，B 与右侧 `Joint1_R` 至 `Joint7_R` 对应；按名字重排后发送 `positions`。这是该桥的约定，不是本次物理侧别验证。
- [参考源码] 同目录 `robot_node/marvin_ros2_control_wb/src/marvin_robot.cpp:101-149` 从 `m_Out[0]/[1]` 依次提取 A/B 七轴状态，位置与速度乘 D2R 后输出，力矩取 `m_FB_Joint_SToq`；`marvin_robot_node.cpp:493-510,702-723` 发布 14 关节状态，并将两侧 ROS 位置命令弧度乘 180/π 转 SDK 角度。`marvin_robot.cpp:203-214` 调用对应 `OnSetJointCmdPos_A/B`。因此该参考通路是位置目标，不能把 DROID 的速度直接当位置；转换、时间步和执行策略尚待设计验证。
- [安装声明] `/usr/local/include/marvinsdk/FxRtCSDef.h:33-50,68-69` 含 7 轴位置、速度、位置指令、力矩反馈、帧序及位置命令。帧序模 1000000，不是采样时间戳。参考节点 `marvin_robot_node.cpp:493-495` 用 `this->now()` 在发布时标记，不证明设备测量时刻；重复 SDK 缓存也不能当新帧（历史控制参考 `/home/nvidia/cph_dev/mios_marvin/docs/MARVIN_CONTROL_REFERENCE.zh-CN.md:58-66`）。具体实测顺序、正方向、零位、控制周期和当前运行发布者未核验。
- [参考资料] `/home/nvidia/cph_dev/tianji_quest_nova/provenance/interface_audit.zh-CN.md:45-47` Quest 输入为 head-relative，而 APEX 相关输入使用 `tracking_base_link`；不能直接等同。当前调查未确认天玑相机外参、机器人基座/工具坐标、位姿方向或图像与关节的共同时间基准。关节数据本身不是笛卡尔位姿。

### 夹爪与相机

- [当前项目源码] `/home/nvidia/cph_dev/tianji_quest_nova/scripts/nova_gripper.py:91-112` 按侧发布 Float32 至 `/tj/control/gripperValueL/R`；`src/tianji_nova/gripper.py:137-161` 根据新鲜输入映射到归一化目标，可反向与缩放。`config/nova_gripper.yaml:1-5,26-45` 记录右侧目标增大为闭合的台架验证、右侧 invert=true 和 0.10–0.45 输出范围；左侧方向未验证。此为历史配置与记录，不证明当前设备状态或完整行程。
- [历史接口审计] `tianji_quest_nova/provenance/interface_audit.zh-CN.md:24-43` 记录命令 0..1，反馈 `Float32MultiArray` 及错误话题；原生驱动源码不完整，现场反馈数组元素、单位、方向、新鲜度不能据此确定。历史分时图中存在 `playback_node`、VR 等发布者，不能据此推断当前唯一命令源。反馈应独立于目标记录，不能拿命令值冒充实测夹爪位置。
- [历史安装包静态审计] `tianji_quest_nova/provenance/TIANJI_CODE_LOCATIONS.zh-CN.md:24-42`：配置 head_left/right 与 wrist_left/right 四槽，媒体主要由原生组件处理；配置帧率不等于实测。JPEG mosaic 和 WebRTC 配置不证明可获得独立外部/腕部 RGB、对应关系、图像采集时刻或与机器人状态同步。该文中的服务 inactive 是 2026-10-26 快照，不代表当前状态。

## 最小缺失样本与后续条件

先选定单侧、任务、外部与同侧腕部视角和控制链；取得一段带任务文本的真实连续示教，逐帧保留原始图像及采集时间、两视角标识/标定、同侧按名称排序的关节位置与时间/帧序、真实夹爪反馈及其字段解释、当时发送的动作目标与时间、控制模式和动作周期。明确各时钟来源、对齐方法及允许时间差，保留缺帧与反馈新鲜度信息；还需确认速度动作到位置通路的尺度/周期、夹爪开闭和设备坐标映射。仅图像或仅状态不能证明动作回放，单条同步样本可检查输入格式，但不能证明完整轨迹或泛化。离线对齐与回放检查、设备采样、实机动作分别验证；任何设备连接、动作或模式切换需另行授权。
