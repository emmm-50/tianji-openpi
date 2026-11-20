# 末端目标、原生 IK 与 Host mock

下午直接接机请先读 [2026-11-20 接力说明](HANDOFF.zh-CN.md)：原始 Base 末端路线与 1500 原生关节路线分开交接。

本目录实现并验证以下离线管线：

```text
假末端位姿 + 假关节反馈
    → APEX QpControllerCore（VLA 专用任务配置）
    → 右臂七关节绝对角 rad + 可选夹爪值
    → 安装版 VLA Host 的 ASGI WebSocket 路由
    → 内存中的假发布器与 ACK
```

原始 π₀.₅ base 的在线推理及真实末端解码尚未接入。新增 virtual_sdk 可回放已保存的 base 输出，但使用显式的人造测试映射。所有入口均未连接真实 Host、ROS、mux 或设备。Host mock 使用安装源码中的实际路由、Pydantic 校验和动作处理；仅消息来源、ROS 依赖和发布器被替换。

## IK 稳态误差修复

原通用任务配置同时跟踪右手位姿、保持初始关节姿态，并保持初始右肘方向。在这条录制轨迹中，后两项软目标与右手目标竞争，导致终点保持后仍有偏差。相同轨迹、初始状态与 1 秒保持时间的对照结果如下：

| 配置 | 保持后位置误差 | 保持后姿态误差 |
| --- | ---: | ---: |
| 原默认配置 | 8.079 mm | 0.04552 rad |
| 仅取消关节姿态保持代价 | 3.131 mm | 0.02689 rad |
| 仅取消右肘方向软任务 | 5.928 mm | 0.02730 rad |
| 同时取消这两项软目标 | 数值精度附近 | 约 3.36e-10 rad |

修复只作用于 `native_ik/` 中的 VLA 专用适配器：`posture_cost=0`，任务配置不包含右肘方向目标。左手、左肘任务、速度阻尼及模型关节限位、速度和碰撞配置继续保留。未修改 APEX 安装或已有遥操配置。

这证明本段模型轨迹上的稳态偏差得到解决，不代表真实机械臂精度或所有目标可达。完整对照保存在 `evidence/base-eef-ik-20261119/ik-fix-comparison.json`。

## 接口与复跑

- [纯 IK 进程](native_ik/README.md)：stdin/stdout 每行一个 JSON；一次初始化完整 14 轴状态，后续每个请求推进一个 2 ms 求解步。目标为模型 world 坐标中的 `right_tool` 位姿，位置单位米、姿态为 xyzw 四元数。`ok` 表示本步求解成功，是否到位要看残差。
- [Host mock](host_mock/README.md)：调用真实 `/ws/action?ack=true` ASGI 路由，核对 ACK 和假发布器捕获值。只转发右臂关节与可选夹爪字段，不转发 IK 诊断。

在天玑工作区执行：

```bash
cd /home/nvidia/cph_dev/pi05
source /opt/ros/humble/setup.bash
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
cmake -S eef-control/native_ik -B /tmp/pi05-eef-ik-build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/pi05-eef-ik-build -j1
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 eef-control/host_mock/test_host_mock.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 eef-control/host_mock/test_ik_host.py /tmp/pi05-eef-ik-build/native_ik /home/nvidia/cph_dev/pi05/eef-control/native_ik/ik_tasks.yaml
rm -rf /tmp/pi05-eef-ik-build
```

联调用例包含保持目标和 world X 增加 1 mm 的假目标，确认关节输出确实变化，并按值到达 Host 假发布器；左臂不发布。非法关节消息、失败 IK 和非有限夹爪值不会通过对应处理环节。安装版 Host 本身缺少夹爪有限性校验，本适配器在生成消息前拒绝非有限夹爪；没有修改安装软件。

## 虚拟 SDK 联调

[virtual_sdk](virtual_sdk/README.md) 使用已保存的真实 base `world_eef` 50×32 原始数组，通过人造的小范围位置、旋转和夹爪映射生成测试目标，再运行现有 IK、真实 Host ASGI 处理和内存 FakeSDK。SDK 的输入来自 Host 假发布器捕获值，不旁路 Host；每帧检查关节及夹爪回读，非法输入不得改变 SDK 状态或写入次数。

这验证软件接口传值，不需要真实机械臂或启动真实 ROS 节点。50 帧是保存输出的开环回放，50 次独立 ASGI 调用，不是新观测驱动的策略闭环，也不覆盖真实网络连接。人造映射的通道、尺度和参考系仅供虚拟测试，不能用作原始 base 的已验证末端动作解码器。

## 验证边界

现有测试使用假定固定的左臂姿态、安装版 IK 静态库与本机 DAQP 0.8.5 扩展。当前验证不涵盖真实网络传输、ROS 发布、夹爪方向/单位、物理碰撞间隙、实时调度或 VLA 动作语义。原始 base 的推理与末端解码仍需在资源空闲后独立核实。
