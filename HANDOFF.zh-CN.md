# π₀.₅ 接续记录：契约调查与合成离线回放完成

## 最新验证：Panda 与天玑右臂的短段 FK 及离线重定向（2026-11-12）

取已保存 48 个实时动作块的前三步。使用 DROID 固定提交 33ae6a6 的 Panda MJCF 和既有天玑右臂纯计算 libKine，分别比较各自起始法兰坐标中的相对运动。Panda 使用和天玑保存状态相同的数值作虚拟起点，未假定物理姿态等价。比较对齐的是初始法兰坐标，未标定 TCP 或 DROID wrist_site 与天玑夹爪之间的物理变换。

按安装配置的名义位置和 J6/J7 耦合约束，共同有效 47 块。第三步同序映射的位移向量误差中位 39.7 mm、方向差 48.1°；在该姿态按雅可比拟合固定关节重排、正负和尺度后分别为 19.8 mm、19.6°。将同一映射搬到另一两机均可用的虚拟初始姿态，方向差中位约 163.3°。结果支持姿态相关的末端重定向，未穷举所有跨姿态拟合方案。

再把 Panda 逐步法兰相对运动作为天玑名义末端目标。迭代阻尼雅可比法在每个静态样本检查安装配置的单轴和 J6/J7 耦合限位，144 个点中 141 个在 1 mm 和 1° 的数值阈值内，45/48 块三个点均满足。以 15 Hz 差分，仍有 4 块速度和 7 块内部加速度超名义限制。未做工具/环境碰撞、物理外参或轨迹执行。无设备连接、模型重跑或动作。

[固定映射和姿态敏感性](offline-replay/evidence/fk-comparison-20261112/independent-review.json) · [迭代重定向数值对照](offline-replay/evidence/fk-comparison-20261112/iterative-retarget-reference.json)

## 最新验证：已保存动作块的离线轨迹与夹爪漏答（2026-11-12）

离线分析 48 个实时动作块及 1 个真实回放动作块，每块从对应保存的右臂反馈独立起算。候选按轴序/正向相同、前七维裁到 [-1,1]、DROID 参考 0.2 rad/步与 15 Hz 积分。最后一维用 >0.5 标记闭合意图，其余标记张开；历史右侧归一化目标增大对应闭合，实际开口及端点仍未标定。轴对应和时标未建立为天玑控制契约。

纯计算 CCS696 libKine 跑完 784 个法兰位姿，最大首末位移 0.556 m。按主控安装 APEX 配置的名义限制复核，48 个实时块中 21 个位置越界，3 个 J6/J7 耦合越界，12 个相邻步加速度越界，离散速度无越界。最差 J4 为 −247.82°，比 −140° 下限低 107.82°。取前 8 步仍有 13 个实时块位置越界。按同一离散时标假设从静止起步，仅第一步也有 31 块超过名义加速度。两套名义配置的限制有差别，均未作为实机生效限制验证。无碰撞、工具 TCP、环境或控制验证，无模型重跑和设备连接。

夹爪并行只读调查确认，SDK 的 `OnSetChDataB` 只写单槽待发送缓冲，异步 `CRobot::DoSend` 调用 274 字节数据报 `sendto` 后清 pending，未检查返回值。应用提交成功无法证明发包成功；现有日志无法定位网口、控制器、CAN 或电机。下次可对齐 SDK 提交、控制器网口双向流量和被动 CAN 时间点定位，无需移动设备。

[轨迹摘要](offline-replay/evidence/action-trajectory-review-20261112/summary.json) · [代表轨迹](offline-replay/evidence/action-trajectory-review-20261112/representative.csv) · [安装配置对照](offline-replay/evidence/action-trajectory-review-20261112/independent-review.json) · [夹爪调查](contract/RIGHT_GRIPPER_READONLY.zh-CN.md)

## 最新验证：实时输入至常驻推理（2026-11-12 15:05，北京时间）

CSI0 头左、CSI5 右腕实时取帧，SDK B 侧七关节与右夹爪只读反馈，同窗输入本机常驻服务。最终 30.15 秒内尝试 59 轮，完成 48 次有限 float64 15×8 推理（1.59 次/秒），另 11 轮因夹爪反馈缺失而跳过。主机端到端中位 522.2 ms、P95 575.4 ms、最大 625.2 ms，服务端中位 481.5 ms。输出只落盘，无动作下发，未保存实时图像。两路相机与 SDK 均已释放，常驻服务仍健康且 PID 未变。

夹爪在 SDK 提交成功后仍可能在 400 ms 内没有回包。已安装 ARM64 SDK 的 `CRobot::OnSetChDataB` 返回成功只证实数据复制进 SDK 待发送缓冲区。现有权限下未能抓取控制器网口，无法判定下游丢失环节。无重试 30 秒基线为 27/63 跳过（42.9%）；50 ms 后重发同一 0xCC 一次，20 轮触发重试，其中 9 轮随后取得回包，最终 11/59 跳过（18.6%）。回包因果和夹爪源新鲜度仍未证实。此次无机械臂控制、模式、使能或夹爪动作。新增代码由主 Agent 在天玑复核，未提交 DSH。

[采集及推理时序复核](offline-replay/evidence/live-right-20261112_150459_559859520/latency-review.json) · [运行说明](offline-replay/README.zh-CN.md)

## 最新部署：天玑本机常驻推理（2026-11-12 14:48，北京时间）

已启动 nvidia 的用户级 `pi05-inference.service`。服务复用单帧回放的策略构建，沿用 JAX sm_87、autotune=4 和现有权重，用已保存的真实右侧观测预热后，仅监听 `127.0.0.1:8000`。本次从 ExecStart 到健康检查成功 73.23 秒，进程打开 Jetson GPU 设备。

用真实观测在同一 WebSocket 上连续请求 10 次，重连后追加 2 次，全部返回有限 float64 15×8。服务端推理中位 466.7 ms，本机往返中位 470.4 ms，进程未重启。另用文档中的上游 OpenPI 客户端成功调用一次。服务持续运行，无相机或 SDK 接入，无机械臂控制。已为 nvidia 启用 linger，SSH 退出不影响服务；主机重启后需手动启动。部署代码由主 Agent 在天玑复核，未提交给 DSH。

[运行与客户端用法](offline-replay/README.zh-CN.md) · [连续推理验收](offline-replay/evidence/real-right-20261112_144023_243023462/service-review.json)

## 最新完成：右侧真实输入离线回放（2026-11-12 14:42，北京时间）

用户授权读取并确认机械臂当前独占，机械臂运动及可能造成危险的行为仍需授权。一次现场采集得到预热后的 CSI0 头左与 CSI5 右腕 RGB8（640×496）、SDK B 侧七关节弧度及一次右夹爪 0xCC 状态刷新回包。B 侧帧序 759012，报告模式 0。两路相机和 SDK 均正常释放。未发送运动、模式、使能、清错、增益或夹爪动作命令。

主机观测跨度 10.46 ms，曝光同步和夹爪源新鲜度未验证。头左可见桌面橙子，右腕当时未见。夹爪电机反馈 1.2648 rad，以安装软件目标范围 0–1.6 rad 反算模型输入 0.79049，物理开口及 DROID 语义等价性未验证。任务为 “Pick up the orange on the table.”。

`offline-replay/pack_capture.py` 生成真实双图与状态 NPZ，经主 Agent 对原始图像、角度、夹爪回包和 NPZ 独立核对。既有 JAX sm_87 环境以 autotune=4 在 cuda:0 调用一次官方 `pi05_droid`，输出有限 float64 15×8，`tianji_command=null`。此为真实输入到模型输出验收，动作映射、周期、抓取效果及硬件闭环仍待验证。转换代码由主 Agent 在天玑核对，未提交给 DSH。

- [原始采集复核](offline-replay/evidence/real-right-20261112_144023_243023462/main-capture-review.json)
- [真实输入 NPZ](offline-replay/evidence/real-right-20261112_144023_243023462/observation.npz)
- [模型复核](offline-replay/evidence/real-right-20261112_144023_243023462/main-replay-review.json)
- [原始模型输出](offline-replay/evidence/real-right-20261112_144023_243023462/replay/actions.npy)

## 最新进展：复用 Argus 双路相机（2026-11-12）

Tianji 资源索引指向 `/home/nvidia/Tianji/resources/camera_projects/argus_isp`。开发和验证使用 `/home/nvidia/wsb_ws/resources/camera_projects/argus_isp/argus_show.py`。实测 CSI0 头左和 CSI5 右腕的方向在180°旋转后正常，约1.7秒时两路明显偏青，约8.6秒且AE/AWB已锁定时明显减轻。头左可见橙子，右腕当时未见。现场对照和相机停止证据：`/home/nvidia/wsb_ws/records/acceptance/right_argus_compare_20261112_143639_205532/compare.json`。

`offline-replay/capture_once.py` 已改用上述Argus管线/解码，5秒预热后请求AE/AWB锁定并输出640×496 RGB8。默认计划、离线自检和语法检查通过；独立只运行新入口的相机部分，两路均取帧且释放，见同目录 `capture_once_camera_review.json`。记录为主机取帧时间，曝光时间及传感器同步未核验。本轮未连接SDK、未运行完整采集或模型。下一步是确认一次右臂关节反馈只读采集的授权，再推进同期状态及离线回放；任何机械臂动作需要单独授权。

更新：2026-11-12（Asia/Shanghai）。本次授权范围内的安装与完整离线功能验收已通过，主 Agent 已独立核查。当前采用 `envs/openpi-sm87` + `jax-sm87/run_offline.py`，显式 `XLA_FLAGS=--xla_gpu_autotune_level=4`；运行命令、版本、证据和天玑适配缺口见 [中文部署记录](README.zh-CN.md)。

## 最新实测：精简工具右B只读成功（2026-11-12 14:13）

用户授权一次只读实测。现场未发现可复用本机SDK owner，现成工具建立一次临时会话：B侧仅2个0xCC状态刷新和12个0x33参数读取，返回ID0x12/2、编码范围12.5/30/10，两次状态回包报告On，SDK释放成功、进程退出。没有模式、使能/失能、运动或参数写入；本轮没有读取机械臂模式，不能追加mode3证明。主Agent逐条核对原始发送和返回。

按工具项目当前AGENTS，实测原始证据及硬件摘要保存在wsb_ws；唯一原始目录为 /home/nvidia/wsb_ws/records/acceptance/gripper_read_B_20261112_141302/，含result.json、gripper_events.jsonl、review.json和main-review.json。S08仍部分完成。只读接口实测通过不证明实际开口、夹持力、源新鲜度或请求因果，本轮单次试验已结束，无重试。

## 最新完成：DSH精简旧管理读取工具（2026-11-12）

用户明确授权指定文件经DSH审查后，按建议删除机械臂观测/版本及伺服前置查询、队列安静要求、重复耗时拒绝，并精简对应夹具/审核脚本。纯读报文及会话边界保留，真实目标已构建；直接相关离线回归与独立审查通过，未实机执行。详见 [右夹爪只读调查](contract/RIGHT_GRIPPER_READONLY.zh-CN.md) 顶部和 [本轮采纳记录](offline-replay/evidence/gripper-mode3-20261112/dsh-simplification-applied.json)。以下仍保留队列/版本/机械臂条件的文字均属此前阶段，不作为新版要求。无需重复全套验证，不以测试条数作为成果。

## 最新修改：旧管理读取工具取消状态准入（2026-11-12）

按用户要求直接修改wsb_ws现有management读取工具：模式/运动/错误与夹爪On/Off/Fault/温度只作观测，不再阻止只读查询；保留原会话、版本、协议、报文白名单、队列和期限，不改控制工具。已构建，22项协议与16项录制离线检查通过，主Agent独立复跑录制回归通过，无设备执行或DSH外发。S08仍部分完成，原队列静止条件可能阻止持续反馈查询。说明与证据见 [右夹爪只读调查](contract/RIGHT_GRIPPER_READONLY.zh-CN.md) 顶部；不再把以下历史mode0/Off限制当成新版行为。

## 最新进展：右夹爪现有只读反馈已读通（2026-11-12）

临时热点SSH地址172.20.10.2，沿用原别名身份，未改配置或大量下载。两名Terra调查和读取、Sol独立检查安装二进制，主Agent核对实际数据：直接复用现有 /tj/info/gripper_feedback_R，约2秒399条，五字段为电机位置/速度/力矩/MOS温度/电机温度；_R_err=[1]是电机上报On。另在独立近时窗口只收vcan1，看到86帧0x12右反馈，未发送任何帧。

现场已有marvin_robot_node占SDK与dm_motor_test运行，systemd单元inactive不代表无进程。独立SDK候选在连接前因owner退出，随后只订阅现有链路；短发现窗口未见发布者的结论已由5秒发现更正。没有切模式、调用Ready、使能/失能或控制。当前arm_state/robot_state为ready遮蔽的[-1,-1]，不能证明当前mode3；旧管理工具mode0条件不能当成SDK硬约束。完整接口、模式边界及证据见 [右夹爪只读调查](contract/RIGHT_GRIPPER_READONLY.zh-CN.md)。后续复用该反馈，仍须解释物理开口归一化和同期观测；无需先切mode0。此前11月6日状态仅为历史。

## 最新成功：有限SDK关节读取（2026-11-06 11:30）

用户说明另一电脑不在开发状态、操作不会影响它；读取类继续授权，不再等待同一项会话确认。现有readonly_capture首轮因PROCESS_SCAN_DEADLINE在连接前退出；无SDK的20秒主机探针通过后，原条件不变的第二次读取成功：约2.013秒99帧，双侧帧序各推进98次，14轴错误查询全0，控制器返回版本100343024，current_mode全程[3,3]。SDK释放返回成功、进程退出。主Agent独立核对帧数、有限值、时间和模式；证据 [live-joint-main-review.json](offline-replay/evidence/live-joint-main-review.json)，原始结果在 offline-replay/evidence/live-joint-read/pi05_readonly_20261106_113010/，首错另目录保留。

没有目标/使能/模式/清错或夹爪控制。现成夹爪管理读取工具要求双臂mode0，而实读为3/3，故不运行它、不切模式。相机与关节并非同期，未拼假同步样本或重跑模型。下一步缺口是右夹爪反馈语义、共同任务视野与同期完整观测；腕部姿态调整等控制需单独授权。细节见 [右侧方案](contract/REAL_SAMPLE_PLAN.zh-CN.md) 首节。以下较早现场记录保留其时序，不能替代本次成功读取。

## 当前授权与现场读取进展

用户已授权读取类操作，机械臂/夹爪控制仍需另行授权，不再为只读查询、反馈订阅或相机读取重复请示。已核对域24/Fast DDS及服务：Backend运行，其余Robot/Tool/Camera/Teleop未运行，无关节/右夹爪反馈发布者。复用已有Argus Stream读取CSI0头左和CSI5右腕各一帧，1280×992 RGB，管线已停止。主Agent独立复核原图：头左倒置、可见桌面；右腕朝地面，不具共同任务视野；接收时间差41.17ms不是源同步证明。尚未形成完整观测，也未重跑模型。

用户确认双臂静止，但另一电脑可能仍连接SDK。因此本轮未建立SDK会话，未启用Robot/Tool、使能或控制。现成readonly_capture仅含关节读取，不含夹爪分支。下一步先确认已有远端SDK会话归属，或由已有会话提供反馈；腕部姿态调整属于控制，应另行授权。详细证据与当前方案见 [右侧采样方案](contract/REAL_SAMPLE_PLAN.zh-CN.md) 最新现场结果；证据 live-state-inspection.json、live-camera-inspection.json、live-camera-main-review.json 位于 offline-replay/evidence。

## 最新补充：右侧真实样本方案

用户提供 /home/nvidia/Tianji/resources/handeye_calibration 和 camera_projects 后，已找到并核对 D435单图+七轴的真实静止历史样本、四台SH5逐台内参及D435候选外参；另有 ~/.ros/log 下无图像的MCAP状态包。原限定目录检索结论保留其范围，不能再泛称没有真实样本。尚缺完整同期双图、真实夹爪反馈与任务文本。

用户已选首轮右侧，两名gpt-6.1-terra/medium分别核对样本与录制入口，主Agent独立核对PPM、末帧元数据和七轴与既有解码记录一致性。见 [右侧最小真实样本方案](contract/REAL_SAMPLE_PLAN.zh-CN.md) 和 [离线证据](offline-replay/evidence/real-sample-review.json)。没有补假值NPZ或运行模型；当时仅授权离线；最新读取授权与现场结果见本文首节，控制操作仍需单独授权。旧完成事项无需重跑。

## 最新阶段与接续入口

本阶段由两名 gpt-6.1-terra / medium 子 Agent 分别调查天玑契约和实现回放，主 Agent 独立核对实际源码、上游依据、原始数组及测试。用户要求主 Agent Standard、子 Agent Fast；委派接口未提供 Fast 档位参数，未修改全局模式。

- 先读 [天玑观测动作契约](contract/TIANJI_CONTRACT.zh-CN.md) 和 [DROID 契约](contract/DROID_CONTRACT.zh-CN.md)，再读 [单帧离线回放](offline-replay/README.zh-CN.md)。文档区分安装声明、静态参考、历史记录、合成软件证据和硬件未验证项。
- 限定项目与常用录制格式检索未发现完整真实同步数据；唯一新 NPZ 是明确标记 synthetic 的随机样本，各流时间戳为空。不能称为真实天玑回放。
- `offline-replay/replay.py` 读取 NPZ 并只调用一次官方 Policy；原环境/权重/缓存与 autotune=4 不变，输出为 finite float64 (15,8)，exit=0。原始模型数组、示例 threshold/clip 数组及元数据在 `offline-replay/evidence/synthetic-result/`。`tianji_command=null`，没有实现或输出物理关节映射。
- 主 Agent 独立审读完整新代码、核对官方变换顺序及保存的输入/输出，逐值确认示例后处理；最终语义测试覆盖状态顺序、RGB 通道、非方图 resize/pad、mask、输出切片、0.5 阈值和裁剪，exit=0。证据 `offline-replay/evidence/main-review.json`、`main-semantics.log/.exit`。未重跑模型或测速。一次模型调用后仅统一 num_steps 常量及补元数据说明，原始推理证据未改写。
- 官方 DROID 上游参考固定为 `33ae6a67274f36d2e29525b86f23a56616ef43a7`，主 Agent 独立核对速度到增量的0.2缩放以及夹爪宽度公式；这不是训练版本或天玑兼容证明。旧 ROS 参考 A=左/B=右、七轴命名与 rad→deg 转换有源码依据，014 SDK 位置目标 deg 有安装头文件依据；现场物理对应和控制周期仍未知。
- 本阶段新源码没有 DSH 外发授权，按用户要求由主 Agent 本地审查。没有连接/驱动臂、夹爪或相机；未启动 ROS/SDK 控制或策略服务器，未改系统网络、安装、提交或推送。GPU Torch 暂缓。天玑仍是唯一开发区，bot 不维护副本、不建 worktree。

### 下一次应做什么

先确定所选单侧、任务、实际控制链和外部/同侧腕部相机。最小输入验证需要一组有来源的双图、按关节名排序的七轴真实状态、真实夹爪反馈及每流时间戳/时钟域；动作映射和周期验证还需连续短片段，包含实际发送目标、反馈、模式与周期。确认关节零位/符号/单位与形态对应、夹爪开闭/行程/反馈字段、相机视角/标定/同步误差、动作块执行/重规划及停止条件之后，再另行授权设备采样或动作。不能把 `15×8` 或 DROID 的 `0.2` 系数直接用于天玑，也不能用命令值当实测反馈。

当前无待等待的构建、测速或回放任务。无需重建 JAX、重下权重或重复30轮测速。后续模型适配/微调尚未开始。

## 已完成的环境事实（保留上阶段证据）

- 官方 JAX tag `jax-v0.5.3`，commit `c8032a9904eeb2410995425f817929f507fe22d5`，PJRT wheel构建exit=0；wheel为 `jax-sm87/wheels/jax_cuda12_pjrt-0.5.3-py3-none-manylinux2014_aarch64.whl`，62,711,805字节。wheel与安装后实际插件均确认含sm_87，共35个cubin；无需重建或轮询旧任务。
- 只在 `envs/openpi-sm87` 用本地wheel --no-deps安装；JAX/jaxlib/kernel plugin/PJRT均0.5.3，Python3.11.18。实际进程加载系统CUDA12.6/cuDNN9.3，没有安装NVIDIA pip SBSA库。
- autotune=4下同步GPU矩阵乘及卷积通过；完整官方 `pi05_droid` 两轮合成观测、10采样步，cuda:0，actions均float64(15,8)且finite，exit=0。
- 模型加载 20.299秒，首轮 50.826秒，热轮 0.514秒。RSS峰 17,240,832KiB；JAX峰 7,114,114,560字节，pool峰 8,587,837,440字节；统一内存不能相加。这是两轮功能验收，非正式性能/稳定性测试。
- 共享权重 `weights/pi05_droid`：20对象共12,429,488,598字节；主Agent再核对已有官方清单的各文件大小，全一致、无.partial；已实际再次加载。原权重与已缓存tokenizer不重下，无需HF登录，Gemma条款用户已同意。
- 官方openpi commit `215abfb217dbac7d5f1273282331b9b1866c0479`，源码工作区干净。

## 资产与边界

所有源码、环境、权重及证据在天玑 `/home/nvidia/cph_dev/pi05`，SSH别名 `TianJi-Codex-huawei`。bot PI0仅归档对话，不维护平行源码。
保留旧 `envs/openpi`、根 `run_offline.py`、`cache/` 结果；旧热轮1.238秒依赖autotune=0，是历史两轮基线。新证据在 `jax-sm87/evidence/`，其中 `main-review.json` 为主Agent独立验收，`offline_result.json` 为模型原始结果；旧日志不覆盖。
GPU Torch继续暂缓，保留 `torch-cuda/` 准备文件，不编译、安装CUDA Torch或转换权重。没有机器人、夹爪、相机、ROS/SDK、模式或策略服务器操作，没有系统/网络改动、提交或推送，不影响他人进程。

## 最新多轮对照

同一个新环境分别显式autotune=4/0、独立新进程串行，每组3预热+30测量，共66次输出均float64(15,8)且finite，exit均0。4组中位0.499802s/P95 0.507034s；0组中位1.376856s/P95 1.393424s。本次中位约快2.75倍、耗时少63.7%；首轮编译/调优更慢，未测试长期稳定或机器人闭环。逐轮数据和主Agent独立重算在 `jax-sm87/evidence/benchmark-autotune{4,0}.json` 与 `benchmark-main-review.json`，命令和口径见部署记录。旧两轮数据未覆盖。
DSH建议的num_steps单一定义已采纳；多轮代码补审无须修改，两次结果在 `jax-sm87/evidence/dsh-review-1.json`、`dsh-review-2.json`。

## 后续

DROID/Franka 单臂权重尚未适配天玑。静态契约与合成回放已完成，后续工作以本文“下一次应做什么”及两份契约文档为准，不直接把 15×8 输出发送设备。
私有 [issue #1](https://github.com/emmm-50/tianji-openpi/issues/1) 已按实际成功更新并关闭为completed；[issue #2](https://github.com/emmm-50/tianji-openpi/issues/2) 保持暂缓。只链接上游，不公开发帖或推送源码。
用户在本对话明确授权限定源码发送至DeepSeek API进行DSH只读审查，已完成两次审查；建议采纳和补审结论见上文。此前缺少外传授权的拒绝已由此次明确授权补足，不据此扩大到其他源码/权重/凭据。
