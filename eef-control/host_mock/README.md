# VLAHost 离线 mock

此目录只在进程内导入已安装的 `/opt/kernelmind/apex/install/vlahost/lib/python3.10/site-packages/vlahost/server.py`，向其 FastAPI 应用发送进程内 ASGI WebSocket 事件，经过 `/ws/action?ack=true` 路由、JSON 解码、`ActionRequest` 和 `VlaHostNode.apply_action`。ROS 模块、ASGI 事件、时钟及发布器均为假对象；导入后恢复 `sys.modules`；不运行 FastAPI 生命周期、不创建 ROS 节点、不使用网络或设备。不发送 lifespan 事件，因而不会运行真实 startup/shutdown；测试覆盖 ASGI 路由和处理函数，不等于真实网络传输、部署生命周期、ROS、mux 或机械臂验收。

```bash
cd /home/nvidia/cph_dev/pi05/eef-control/host_mock
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 test_host_mock.py
```

验证右臂 7 个关节与夹爪值传递、实际 ack、没有左臂消息，以及关节长度、非有限值、类型不合法时拒绝并不发布。夹爪值只代表消息数值，不说明开闭方向或单位。

已安装 Host 的 `ActionRequest` 与 `apply_action` 未拒绝非有限夹爪值：独立 mock 观察 `gripper_right=NaN` 得到 success 且发布 NaN。不要把该路由视为提供了夹爪有限性校验；本目录不修改安装软件。

`host_mock.py` 可从 stdin 读取成功 IK 结果，仅转发 `jointcmd_right`、可选 `gripper_right`，不转发诊断字段；拒绝非有限夹爪，失败结果不会发送。它没有网络连接，也不是实际 Host 服务器。

联调命令（原生 IK 临时编译产物路径以实际构建结果为准）：

```bash
source /opt/ros/humble/setup.bash
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 test_ik_host.py /path/to/native_ik ../native_ik/ik_tasks.yaml
```

使用固定假关节，先求末端保持目标，再在同一 IK 进程求 world X +1 mm 目标，验证相对保持步的关节值变化且输出经 ASGI 到假发布器；单步结果不等于已经到达目标；这不验证物理运动或 base 模型输出。
