# VLAHost 离线 mock

此目录只在进程内导入已安装的 `/opt/kernelmind/apex/install/vlahost/lib/python3.10/site-packages/vlahost/server.py`，向其 FastAPI 应用发送进程内 ASGI WebSocket 事件，经过 `/ws/action?ack=true` 路由、JSON 解码、`ActionRequest` 和 `VlaHostNode.apply_action`。ROS 模块、ASGI 事件、时钟及发布器均为假对象；导入后恢复 `sys.modules`；不运行 FastAPI 生命周期、不创建 ROS 节点、不使用网络或设备。不发送 lifespan 事件，因而不会运行真实 startup/shutdown；测试覆盖 ASGI 路由和处理函数，不等于真实网络传输、部署生命周期、ROS、mux 或机械臂验收。

```bash
cd /home/nvidia/cph_dev/pi05/eef-control/host_mock
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 test_host_mock.py
```

验证右臂 7 个关节与夹爪值传递、实际 ack、没有左臂消息，以及关节长度、非有限值、类型不合法时拒绝并不发布。夹爪值只代表消息数值，不说明开闭方向或单位。

已安装 Host 的 `ActionRequest` 与 `apply_action` 未拒绝非有限夹爪值：独立 mock 观察 `gripper_right=NaN` 得到 success 且发布 NaN。不要把该路由视为提供了夹爪有限性校验；本目录不修改安装软件。

`host_mock.py` 可从 stdin 读取成功 IK 结果，仅转发 `jointcmd_right`、可选 `gripper_right`，不转发诊断字段；拒绝非有限夹爪，失败结果不会发送。它没有网络连接，也不是实际 Host 服务器。

常驻接收器可向 `run_action(payload, *, host=None, loop=None, on_right_publish=None)` 传入一次加载的 Host 和事件循环。右臂内存发布器在实际接收时把单调时钟的纳秒数传给回调，调用结果另含路由的 ACK。单条调用可直接使用 `run_action(payload)`。

联调命令（原生 IK 临时编译产物路径以实际构建结果为准）：

```bash
source /opt/ros/humble/setup.bash
source /opt/kernelmind/apex/install/setup.bash
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 test_ik_host.py /tmp/native-ik-build/native_ik /home/nvidia/cph_dev/pi05/eef-control/native_ik/ik_tasks.yaml
```

使用录像相邻帧 300/302 的关节反馈和共享 URDF FK，验证保持和移动目标经过常驻 IK 与内存 ASGI Host，检查 ACK、右关节及没有左臂、夹爪和内部 IK 发布。真实 ROS 消息仅在内存中做 CDR 往返；模拟反馈由接收命令构造，其 header、接收和快照时间经重新初始化关联到下一步结果，并不代表机械臂到位。测试还覆盖非法夹爪、异常四元数和失败后禁止继续。录像 header 时间和 bag 接收时间分别记录；不访问设备或网络。
