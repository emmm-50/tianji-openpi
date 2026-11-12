# 右夹爪只读反馈接口调查

## 2026-11-12：实时推理夹爪漏答的离线定位

上一轮 30 秒试跑未重试 27/63 轮超时。50 ms 后最多重发一次的试跑中，20 轮重发后有 9 轮随后收到回包，11/59 轮最终超时。无重试成功轮从首次提交到应用读到回包的中位约 10.18 ms，轮询周期约 10 ms。不能由此证明回包与某一笔请求一一对应。详见 [原始时序复核](../offline-replay/evidence/live-right-20261112_150459_559859520/latency-review.json)。

本次独立反汇编天玑当前 `/usr/local/lib/libMarvinSDK.so`。`CRobot::OnSetChDataB`（0x197a4–0x19834）写通道、长度、序号和负载至单槽缓冲，置 pending 后返回 true。`CRobot::DoSend`（0x1ad54–0x1ad84）以 274 字节调用 `sendto`，不检查返回值即清 pending。`CRobot::OnGetChDataB`（0x195b0 起）消费接收缓冲。应用有提交、轮询和释放记录，无法证明每次数据报出主机、控制器转换成 CAN、电机回包或响应进入 SDK。此轮未接设备、未采新数据。

下次对齐 SDK 提交与读取记录、天玑控制器网口双向数据报和控制器侧被动 CAN 记录。主机网口抓包可判别主机侧收发，CAN 记录可继续判别控制器转发与电机响应。此前 nvidia 账号对 eth0 的 tcpdump 尝试因权限不足而退出。

更新：2026-11-12（Asia/Shanghai）。用户授权读取，明确不为采集切换机械臂模式。临时热点SSH使用HostName=172.20.10.2，沿用TianJi-Codex-huawei及原主机密钥身份；没有改SSH配置、大量下载、安装、模型运行或控制源码。

## DSH精简已落地（2026-11-12）

用户明确授权限定源码/测试外发DSH审查；首轮达到300秒调用方时限，同会话续接完成。已采纳并实施：删除机械臂10帧观测、版本/伺服前置查询、OnGetBuf/DCSS及帧统计；删除请求前队列安静条件；删除重复8秒及调用后20ms拒绝；删减对应夹具和重复审核状态机。只读选侧/报文解析、会话与取消期限、400ms应答期限、释放和原始事件仍保留。当前真实工具只有6个SDK导入，不再依赖GetBuf/GetIntPara。旧文中“队列安静仍可能拒绝”等为精简前历史描述。

真实目标已构建，直接相关的离线协议/录制回归通过，主Agent核对实际产物和日志，Sol独立审核完成。无设备运行、安装或大下载。未采纳无实际证据的事件上限扩容；成功报告仍须有完整原始读取证据，失败部分结果允许原始候选对应，未恢复配对状态机。见 [DSH结论](../offline-replay/evidence/gripper-mode3-20261112/dsh-simplification-review.json) 与 [采纳和验证记录](../offline-replay/evidence/gripper-mode3-20261112/dsh-simplification-applied.json)。队列数据仍无源时间/因果证明，不能把读到缓存包装为新鲜设备反馈。

## 旧工具限制已按用户要求修改（2026-11-12）

直接修改 /home/nvidia/wsb_ws/native/mios_gripper 的既有管理读取工具及配套审核/测试，没有另建平行采集器。模式、运动、模式变化、错误、夹爪On/Off/Fault与温度改为观测，不再作为读取准入；共享控制观察器和其他控制工具不变。读报文仍为选定侧的0xCC/0x33，会话、版本、路由/长度/RID、超时及原队列策略保留。模式3不再被该工具的机械臂模式条件拒绝。

真实可执行已重新构建；22项协议检查、16项录制检查通过，主Agent独立复跑录制回归通过；无参数计划SDK调用为0、requires_gripper_off=false。没有执行硬件查询，原队列静止条件仍可能拒绝持续反馈。见 [本轮修改复核](../offline-replay/evidence/gripper-mode3-20261112/management-change-review.json)。下文关于旧工具mode0/Off限制描述的是修改前调查事实，原始证据不改写。

## 结论

**现有右夹爪ROS反馈已实际读通，可以直接复用；本次没有切换机械臂模式。** 旧management_capture要求双臂mode0是该工具自身的条件，不是已证实的SDK限制。当前ROS机械臂状态返回[-1,-1]，运行二进制证实它受ready条件遮蔽，因此本次仍不能证明实际机械臂一直处于mode3。

本轮没有启动、停止或接管Robot/Tool/Teleop，没有发送夹爪状态刷新、使能、失能、MIT目标、模式或写参数。实际控制/夹爪进程由既有启动链运行，独立SDK读取器发现现有owner后在连接前退出；随后只订阅已有ROS与只接收vcan1，不建立第二个SDK会话。

## 优先复用的对称接口

| 项目 | 左侧 | 右侧 |
| --- | --- | --- |
| SDK末端接收 | OnGetChDataA(buffer, &channel) | OnGetChDataB(buffer, &channel) |
| ROS反馈 | /tj/info/gripper_feedback_L | /tj/info/gripper_feedback_R |
| ROS状态字节 | /tj/info/gripper_feedback_L_err | /tj/info/gripper_feedback_R_err |
| 当前安装配置 | vcan0，电机ID1 | vcan1，电机ID2 |

SDK每次调用前令channel=1（CAN子通道），提供256字节缓冲；读取的是SDK已接收的队列，不等同主动刷新。不能清缓存、使能电机或发送控制帧来掩盖无数据。左右接口结构对称，本次重点验证右侧；不把左侧行为自动当成右侧硬件证明。

本次右ROS发布者为 /tj/dm_gripper_motor_node，类型std_msgs/msg/Float32MultiArray，可靠、volatile。其五项顺序由实际运行的dm_motor_test二进制与安装结构核对：

| 索引 | 驱动字段 | 解释边界 |
| --- | --- | --- |
| 0 | position | 电机位置解码值；不是已经标定的夹爪张口，也不是模型0..1输入 |
| 1 | velocity | 电机速度解码值 |
| 2 | torque | 电机力矩解码值；不据此宣称夹持力 |
| 3 | mos_temperature | MOS温度 |
| 4 | motor_temperature | 电机温度 |

/tj/info/gripper_feedback_R_err为Int32MultiArray，单项来自反馈首字节高4位：本次[1]为电机报告On，不能误报为“故障1”。该状态是驱动/报文报告，不证明物理夹持或停止。

## 实际证据

- [独立SDK候选首错](../offline-replay/evidence/gripper-mode3-20261112/passive-20261112-132201/result.json)：KNOWN_OWNER_EXECUTABLE，sdk_connection_attempted=false，两侧读调用数均0。空记录是采样未执行，不能说夹爪未回包。
- 当前发现marvin_robot_node占UDP4730及dm_motor_test进程，虽然相应systemd单元仍inactive，说明应按实际进程而非只看服务判断。没有终止或替换这些进程。
- [ROS有效读取](../offline-replay/evidence/gripper-mode3-20261112/ros-rediscovery-20261112-132610/inspection.json)：5秒发现后，约2秒收到右反馈399条、右状态399条；右反馈有11种数组，状态均[1]。常见数组为[-0.0120162964, -0.0073260069, 0.0268626213, 29, 27]。之前较短发现窗口中未见发布者的结论已被本次结果更正。
- [vcan1只接收观察](../evidence/gripper-mode3-20261112/can-read-132622-400812.json)：2秒看到0x2命令类1977帧与0x12反馈类86帧，send_calls=0。保存的右反馈样本DLC8，首字节0x12表示低4位ID2、高4位状态1。命令TX回显未被当成反馈。
- ROS窗口北京时间13:26:15.414–17.469，CAN窗口约13:26:22.401起。两者相近但不重叠，不能逐条配对或证明请求因果。
- [安装接口静态复核](../offline-replay/evidence/gripper-mode3-20261112/installed-interface-static-review.json)记录两份运行ELF、函数/地址、反馈字段与模式遮蔽；主Agent另行核对实际反汇编、重新统计原始ROS记录与CAN标识，见[主Agent复核](../offline-replay/evidence/gripper-mode3-20261112/main-review.json)。

安装dm_gripper.yaml明确feedback_rate_hz=200是重复发布最近解码值的ROS频率，不是CAN接收频率。Float32MultiArray没有Header/源时间戳；变化和高发布频率都不能单独证明每条为新电机数据。vcan上的合法0x12帧也不能单独证明物理CAN来源或完整设备链已验收。

## 模式3问题的准确边界

1. 安装014 SDK头声明OnGetChDataB取得右末端回复，没有给出必须mode0的条件；机械臂mode3与DM电机On/Off或MIT模式是不同状态。
2. 现有被动读取源码使用允许静止mode0/1/3的观察器，没有OnSet/模式/使能调用。现存管理工具另外要求双臂mode0和电机Off，本轮没有删除、放宽或绕过这些条件。
3. 运行marvin_robot_node在未ready分支把实际取到的双臂状态替换成-1，并把同一数组发给arm_state及robot_state；本次[-1,-1]不是mode3，也不能据此判定mode0。
4. 如需严格证明当前mode3下能读，仍需同一观测窗口由现有SDK owner提供未遮蔽的m_CurState[B]，同时记录右反馈。本次未为取得这一证据调用Ready/set_mode或建立第二个SDK会话。

厂商参考refresh_motor_status使用0x7FF、payload [2,0,0xCC,0,0,0,0,0]作右电机状态刷新，0x33为读参数，0x55为写参数。它们解释了主动查询与被动队列读取的区别；本轮现有ROS链已经能读，故未新增探针或发这些查询。厂商KM_gripper入口会使能/发目标，不可作为只读入口直接运行。

## 对π₀.₅采样的影响

右侧真实反馈入口已找到，无须先把机械臂切到mode0。接下来可把该话题纳入现有采集链，保留完整原数组、主机接收时间和来源。剩余是电机位置到实际夹爪开口/模型0..1的映射、反馈新鲜度说明，以及与双图/关节的同期记录；本次不生成假同步NPZ，也不把命令范围0..1.6自动当作已标定行程。
