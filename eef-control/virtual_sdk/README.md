# 原始输出的离线虚拟管线

此实验读取已保存的 `base-actual-20261120.npz` 中 `world_eef` 原始 50×32 数组，不进行模型推理。模型的末端动作合同未知，下面的通道和比例完全是**虚拟测试假设**，不是模型解码方法，不能用于真实控制：

- `p = p0 + 0.01*tanh(raw[0:3])`，world 轴每分量至多 ±1 cm，位移模长最多 √3 cm。
- `R = Rotation.from_rotvec(0.05*tanh(raw[3:6])) * R0`，世界轴旋转向量左乘初始姿态，每分量至多 ±0.05 rad。
- 夹爪值 `(tanh(raw[6])+1)/2` 是无量纲虚拟值，不代表实际夹爪方向或单位。

固定初始关节与工具姿态见脚本，50 帧各执行一次 2 ms 离线 IK 步；然后通过 50 次独立的安装版 Host ASGI 内存调用，从假发布器取出关节弧度与夹爪值，写入内存 FakeSDK 并回读。失败 IK 或非有限夹爪不进入 Host，不更新 FakeSDK。FakeSDK 不调用或模拟厂商 SDK ABI。此为已保存动作块的开环重放，没有新的观测和模型推理，也不模拟物理动力学、真实网络、ROS 节点、mux 或机械臂；残差不代表实机精度，单步也不表示目标已到位。

在天玑复跑：

```bash
source /opt/ros/humble/setup.bash
cmake -S /home/nvidia/cph_dev/pi05/eef-control/native_ik -B /tmp/pi05-virtual-sdk-20261120/build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/pi05-virtual-sdk-20261120/build -j1
export LD_LIBRARY_PATH=/home/nvidia/.local/lib/python3.10/site-packages:${LD_LIBRARY_PATH:-}
cd /home/nvidia/cph_dev/pi05/eef-control/virtual_sdk
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 run.py /tmp/pi05-virtual-sdk-20261120/build/native_ik
rm -rf /tmp/pi05-virtual-sdk-20261120
```

结果为 `evidence/base-eef-ik-20261119/virtual-sdk-20261120.json` 和 `.npz`。复跑会更新这两份结果。
