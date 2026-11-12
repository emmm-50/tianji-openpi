# π0.5 DROID 离线契约

依据天玑本地 openpi 固定提交 `215abfb217dbac7d5f1273282331b9b1866c0479`；本文件为静态代码理解，不是设备验证。

- `src/openpi/policies/droid_policy.py` 的输入是外部和腕部 RGB、七个关节位置、一个夹爪位置与文本；state 依此拼接为八维。`left` 指双目相机的左视图，不指天玑左臂。PI05 的第三张右腕图是零图且 mask 为 false。
- `src/openpi/training/config.py` 的 `pi05_droid` horizon 为 15，模型内部 action_dim 为 32，官方 `DroidOutputs` 截取前八维；`examples/droid/convert_droid_data_to_lerobot.py` 注明前七维为关节速度、末维为夹爪位置。速度数值的物理单位和比例不能从该名称推定。DROID 与天玑关节顺序、正方向和单位尚无对应证据，不能输出天玑命令。
- `examples/droid/main.py` 以 15 Hz 为采集和执行目标，示例将夹爪值严格大于 0.5 映为 1，其余为 0，再将动作裁到 [-1,1]；这是示例后处理，不改变原始模型输出，也不证明天玑兼容。该示例的 (10,8) 断言与本配置 horizon 15 不一致。
- 转换器声明 DROID 通常 15 fps，按 timestep 索引取图，虽然传入 `<camera>_frame_received` 给 `read_camera(correct_timestamp=...)`，固定提交中的该 Reader 未使用该参数。示例从一次 observation 取状态与相机，但推理请求无时间戳；这些代码不证明相机与状态的同步精度或共同时间域。
- 示例将相机 BGR 转 RGB 并按比例补边缩放至 224×224；本回放要求输入已是 HWC uint8 RGB，策略的官方模型变换负责后续 resize/pad。本样本本身为 224×224；未证明真实相机色序或视角。

真实样本的常用格式补查结果及限制见 [天玑契约](TIANJI_CONTRACT.zh-CN.md)。最少还需有来源和任务文本的外部及腕部 RGB、所选侧七关节状态、真实夹爪反馈及其语义、每流采集时间与时钟域及已证明同步关系；之后仍需确定机器人映射、状态单位、速度比例和夹爪方向。合成帧只有软件链路意义。

### 独立的 DROID 上游参考

[DROID commit 33ae6a6 的 IK 转换（2026-11-06 查询）](https://github.com/droid-dataset/droid/blob/33ae6a67274f36d2e29525b86f23a56616ef43a7/droid/robot_ik/robot_ik_solver.py) 中各关节 `relative_max_joint_delta=0.2`、`max_joint_delta=0.2`；对七维输入 `v` 算 `m=max(abs(v))`，若 `m>1` 则整体除以 `m`，然后 `joint_delta=0.2*v`。该实现将所谓 joint_velocity 当作缩放后的步进输入，不能直接认定为 rad/s；[同版本 robot.py](https://github.com/droid-dataset/droid/blob/33ae6a67274f36d2e29525b86f23a56616ef43a7/droid/franka/robot.py) 将 delta 加到读取的关节位置后作为目标。此版本是公开参考，未证明与 π0.5 训练采集版本或天玑部署相同，不能拿 0.2 直接换算天玑。

同一 robot.py 的夹爪反馈是 `1 - width/max_width`，位置命令的目标宽度为 `max_width*(1-command)`：在该实现中 0 对应最大宽度、1 对应零宽度。天玑夹爪方向及真实反馈尚未证实，不能据此映射。
