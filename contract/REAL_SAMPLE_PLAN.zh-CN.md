# 右侧最小真实样本采集方案

## 2026-11-12 真实输入结果

本计划的右侧静止单次采样及离线推理已完成。已取得两路 RGB、B 侧七关节及右夹爪反馈，主机观测跨度 10.46 ms。头左可见橙子，右腕未见。源同步、夹爪源新鲜度、物理开口、动作映射及闭环仍待验证。最新范围、证据和授权见 [π₀.₅ 交接](../HANDOFF.zh-CN.md)；下方方案及此前授权均为历史记录。

更新：2026-11-06（Asia/Shanghai）。用户已选首轮右侧，并已授权所有读取类操作，包括现场查询、现有反馈订阅和相机读取；机械臂/夹爪控制、使能、模式切换等仍需另行授权。天玑为唯一开发工作区。本文件不含可直接执行的设备命令。

## 2026-11-12反馈入口更新

现有右夹爪ROS反馈已实际读通，采集直接复用 /tj/info/gripper_feedback_R；无需为采集切mode0。当前真实机械臂模式被ROS ready哨兵遮蔽，mode3兼容性仍未在同一窗口直接证实。字段、399条反馈与CAN只接收记录、缓存/时间边界见 [右夹爪只读调查](RIGHT_GRIPPER_READONLY.zh-CN.md)。下文“夹爪未取得”等为11月6日历史状态；本次仍缺开口归一化与完整同期样本，未重新采图或运行模型。

## 最新关节只读采样（2026-11-06 11:30，北京时间）

用户进一步说明另一电脑不在开发状态、操作不会影响它，主Agent据此继续已有读取授权，不再将远端会话确认作为等待项。复用现有 readonly_capture，一次原条件采样因 PROCESS_SCAN_DEADLINE 在SDK连接前退出；原始首错保留。随后无SDK的20秒主机监护探针通过，原条件不变的第二次采样成功，没有修改监护、阈值或源码。

- [实际结果](../offline-replay/evidence/live-joint-read/pi05_readonly_20261106_113010/result.json)与同目录frames.jsonl、frames.bin：约2.013秒99帧、双侧序号各推进98次，14轴伺服错误查询均0，controller VERSION返回100343024（不是本机SDK包版本100343014）。
- 主Agent独立核对99条双侧七轴位置/速度为有限数、主机时间严格递增、模式和释放报告；[复核摘要](../offline-replay/evidence/live-joint-main-review.json)保留右侧末帧。SDK释放返回true，进程已退出；不据此宣称机械停止或硬件控制适配完成。
- 全部已保存帧current_mode均为[3,3]。现成右夹爪管理读取器的源码要求双臂mode=0，故未运行该入口、未切模式。该工具的0xCC刷新/0x33读取参数属于主动查询，不等于被动监听，也不自动提供已标定的夹爪开口。
- 关节采样和此前相机双图不在同一窗口，不能直接拼成同步观测。仍缺当前右夹爪反馈语义/开口映射、共同任务视野和同期采样/任务文本。腕部姿态调整、使能或模式切换必须另行授权。
- 本轮只读连接/查询/释放，没有机械臂或夹爪控制、模式切换、清错、模型推理、提交推送或新代码。一次失败不证明owner冲突，主机探针通过也不证明控制器排他。

## 最新现场读取结果（2026-11-06）

- [现场图与服务快照](../offline-replay/evidence/live-state-inspection.json)：Backend运行，Robot/Tool/Camera/Teleop均inactive。Backend实际域24/Fast DDS；本域没有关节或右夹爪反馈发布者，未获得当前关节/夹爪状态。此结论不排除其他域或远端控制器连接。
- [相机读取记录](../offline-replay/evidence/live-camera-inspection.json)：复用既有Argus Stream，仅打开CSI0头左和CSI5右腕各取一帧，两路均为1280×992 RGB，未翻转、未去畸变；两管线均报告停止至NULL，服务仍inactive。原图保存在 evidence/live-camera-inspection 下。
- [主Agent独立复核](../offline-replay/evidence/live-camera-main-review.json)：两张PPM尺寸/像素区及接收差复算一致，已实际查看图像。头左可见桌面但原画面上下倒置且偏青；右腕主要可见夹爪和地面，没有共同桌面任务区域。图像原件未变换。约41.17ms仅为顺序读取的主机接收差，不证明曝光同步。
- 用户已确认双臂静止，但另一台电脑可能保持SDK连接。本机锁/端口空闲不能排除该连接，因此未新建SDK会话、未启动Robot/Tool或发送任何控制。
- 已构建的handeye readonly_capture只有关节读取，无夹爪读取分支；不能声称运行它便可补齐完整样本。它会连接/查询/释放SDK，执行前仍须明确现有会话归属。带OnSetChData的管理程序需要按实际读请求路径审核，不能仅凭名称当成被动监听器。
- 优先方案仍是复用已有状态与图像链；本次已验证独立Argus双路读通，但APEX视频录制/裁分未验证。此项是当时的连接疑问，现已按用户后续说明完成关节只读连接，见本文最新关节采样。读取不再重复请示；任何控制链启用或腕部姿态调整另行授权。

## 本轮结论与已核对样本

优先复用 APEX 的 data_bag_recorder 与 gmsl_quadcam 视频录制，在已有状态发布者上采一段约 5–10 秒的静止窗口，离线选出一组外部图、右腕图、右臂七轴位置、真实右夹爪反馈和任务文本。5–10 秒只是建议采样长度，不是同步精度或性能保证。首轮输入验证无需重做手眼标定，也无需动作目标；动作目标和周期属于后续轨迹验证。

[代表样本证据](../offline-replay/evidence/real-sample-review.json) 指向用户提供的 /home/nvidia/Tianji/resources/handeye_calibration 中 handeye_custom_20261104_001：
- 头部 D435 的 P6 RGB 图为 640×480，像素区 921600 字节。保存末帧对应 color_number=40；设备标注 Global Time，同时保留主机 monotonic 观察时间。
- 七轴 q_deg、dq_deg_s 与已有 decoded_observations.jsonl 中按帧序和精确 pcap 时间定位的唯一记录逐值一致；原始 pcap 存在。本轮没有重新解码 pcap。
- 主 Agent 独立以标准库核对 PPM 文件、末帧元数据、101 条既有解码记录中的匹配项及原始文件大小，通过；未运行项目模块、模型或设备程序。
- 该样本仍是单视角静止历史记录，B 仅假定右臂，物理轴序和新鲜度未验证；小的主机时间差不是曝光同步证明。缺同一时段右腕图、真实夹爪反馈及任务文本，不生成填假值的 NPZ。
- /home/nvidia/.ros/log/topic_log-2026-11-02-14-25-53-777651/metadata.yaml 另有约300秒关节与双侧夹爪消息，但没有图像；不能与不同时间的手眼照片拼成同步样本。

## 选定数据与复用路径

| 数据 | 首选来源 | 保存与解释 |
| --- | --- | --- |
| 外部 RGB | APEX 已有头部相机；优先评估 head_left / G0 / CSI 0 | 头左不表示左臂操作。先确认任务区域可见、视频布局和方向；D435 是备用视角，不额外默认打开 |
| 右腕 RGB | right_wrist / G3 / CSI 5 | 保留原始视频，核对裁分位置、分辨率、旋转和去畸变后再导出 RGB |
| 右臂七轴 | /tj/joint_states（JointState） | 原联合消息可含双侧，保留 name/Header，离线按已核对的右臂关节名提取；不因此操作左臂 |
| 右夹爪反馈 | /tj/info/gripper_feedback_R（Float32MultiArray） | 保留完整数组；位置字段、单位、开闭与归一化关系须核对，命令值不能代替反馈 |
| 时间 | 消息 Header、bag 记录时间及可用相机时间元数据 | 分流记录 clock domain 和来源；无源时间就注明只有接收时间，报告实际可计算差值，不预设同步阈值 |
| 文本与来源 | 一条用户认可的任务描述及采样元数据 | 保留真实来源、侧别、视角和图像处理过程；不冒称已成功执行该任务 |

官方 recorder 白名单已包含 joint_states、右夹爪反馈及右夹爪目标；图像走独立 video MCAP。通过 /api/v1/record/start 指定状态话题，必须与实际白名单取交集；不能假定任意图像话题都能传入。具体设备调用在授权和现场核对后确定。

data_bag_recorder 在 teleop_replay.launch.py 中是独立 Node，可以作为单独配置的候选；其独立运行、命名空间和服务仍未实测。不要为了录制直接启动 teleop_replay 或 play_back_real_dev 组合，它们还启动 teleop 或 playback。现有 recorder 正在工作时应复用；没有状态发布者时 recorder 不会产生设备反馈。

相机视频请求与状态录制可分别失败，须分别核对 data/video 文件及实际消息。/quad_tile/jpeg/compressed 可以作为现成图像来源的备选，但订阅会触发编码，且不在该 recorder 状态白名单；只有确实需要时才考虑现成 rosbag 订阅路径，不先新写采集器。

## 已有相机资料与剩余问题

- 四台 SH5 各有内参：/home/nvidia/Tianji/resources/handeye_calibration/camera/intrinsics/{head_left,head_right,left_wrist,right_wrist}.yaml；原始标定分辨率2560×1984、8项畸变。图像原方向仍为未独立核验假设，不能直接把K/D套到APEX旋转、缩放、裁剪、去畸变后的图。
- /home/nvidia/Tianji/resources/camera_projects/config/commissioning.json 保存2026-10-24看标号照片的人工安装位置确认。它支持通道对应，不证明今天接线或画面方向。
- handeye_calibration/results/cameras.yaml 只有头部D435候选外参，validation.status=candidate，腕部外参尚无对应完成条目。当前模型输入不直接要求外参，首轮格式/输入验证不把完成所有手眼标定设为前提。
- 仍需现场核对：实际发布者和消息类型/QoS、右臂轴名及单位、夹爪真实字段/单位/新鲜度、视频布局/方向、时间戳含义。没有源时钟证据时仅作接收时间近似对齐，不宣称硬件同步。
- VLA Host /state 使用各路最新缓存，图像 stamp 来源是回调接收时间，不能作为同步输入的主证据。

已有 handeye passive/capture_once.py 是“单相机采样+已有SDK会话的入站FX抓包”，不另建SDK连接，但需要打开相机与sudo抓包，而且只有单图/静止状态，不包含完整双图和右夹爪反馈。它可复用解码与时间记录思路，不能直接替代本方案。collect_once.py 的另一条入口会建立SDK连接，不作为默认路线。GEAC RAW初始化、内核模块操作、重做标定均不在本次需要内。

## 后续授权与交付

1. **现场只读核实已完成，读取类授权持续有效。** 服务、进程、ROS图和现有相机读取的结果见上文；无需为同范围读取再请示。已按用户后续说明完成一次SDK关节读取并释放；保留原有会话检查，不改控制状态。
2. **静止读取在现有授权内。** 只读订阅与图像落盘可以继续；已有两张实图尚无同期状态。现有录制接口若会启动其他控制组件，则先明确该副作用；不发送右臂/夹爪目标、使能、Ready、回零、reset或模式切换。
3. **仅在实际缺服务时另列启动范围。** 独立 recorder、Camera、Robot、Tool 分开说明。默认 Camera 可能启动四路；右侧样本不等于仅打开两台相机。Robot/Tool可能访问控制器，不能用“只读采样”概括其启动。
4. **后续动作示教另行授权。** 才记录发送目标、反馈、模式和周期，定义单侧动作/停止范围。单帧输入检查不需要先执行动作。

采样后的最小产物是原始data/video录制、来源与时间说明，以及在图像/关节/夹爪语义已解释后导出的单帧NPZ。原始字段仍保留；未知归一化不猜补。先验收样本，再决定一次离线模型回放；不自动把模型输出转发设备。

## 静态依据入口

以下均为天玑文件，本轮未启动其程序：
- /opt/kernelmind/apex/install/apex_backend/share/apex_backend/launch/teleop_replay.launch.py：独立 recorder 构造与组合启动。
- /opt/kernelmind/apex/install/recording_playback_nodes_py/share/recording_playback_nodes_py/config/recording_playback.yaml：白名单、data/video目录。
- /opt/kernelmind/apex/install/apex_backend/share/apex_backend/docs/API.md：录制接口及白名单交集。
- /opt/kernelmind/apex/install/gmsl_quadcam/share/gmsl_quadcam/config/quad_quickview.yaml：相机配置、JPEG订阅编码、视频参数。
- /home/nvidia/Tianji/resources/handeye_calibration/{README.md,passive/README.md,camera_profiles.py}：内参、候选标定和被动采样边界。

本阶段使用已有相机读取组件作有限双路读取，保存证据与文档；未新增持久采集器，未操作机械臂/夹爪，未重跑模型、提交推送或DSH外发。
