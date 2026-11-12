# 单帧离线回放

只读 NPZ 并调用一次官方策略；不连接设备、发布消息或生成天玑命令。`actions.npy` 保存模型后处理的原始 15×8 输出，`droid_example_clipped.npy` 是另存的官方示例阈值/裁剪结果，不是天玑动作。`metadata.json` 保存输入来源、时间元数据与运行参数；输入 NPZ 自身保留原始观测。

NPZ 字段：`exterior_rgb`、`wrist_rgb` 为 HWC uint8 RGB；`joint_position` 为 7 维，`gripper_position` 为 1 维，`prompt` 为字符串；`metadata_json` 为 JSON 字符串，应记录真实/合成、来源和每流时间戳、时钟域以及同步依据。脚本不校验同步，也不自动把天玑数据转换成 DROID 语义。相关未知项见 `../contract/DROID_CONTRACT.zh-CN.md`。

```bash
cd /home/nvidia/cph_dev/pi05
envs/openpi-sm87/bin/python offline-replay/test_semantics.py
LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu/nvidia \
 XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_FLAGS=--xla_gpu_autotune_level=4 \
 envs/openpi-sm87/bin/python -u offline-replay/replay.py offline-replay/evidence/synthetic.npz offline-replay/evidence/another-result
```
输出目录必须不存在，避免覆盖旧证据。`evidence/synthetic.npz` 为 NumPy seed 0 合成，不是现场数据。`evidence/replay.log`、`replay.exit` 及 `synthetic-result/` 是一次模型调用的证据，不是基准测试。官方策略加载次序与已有 `jax-sm87/run_offline.py` 相同；因其没有策略工厂，保留少量构建代码重复。

合成样本生成方法：使用 `numpy.random.default_rng(0)`，依次生成两张 `integers(0, 256, (224,224,3), dtype=uint8)` 图，再生成 `random(7)` 关节和 `random(1)` 夹爪，文本为 `do something`。metadata 明确 synthetic、无设备和空时间戳。此样本只检验软件路径，不提供同步真实性证据。此次推理之后代码仅将同值 10 合并为单一局部变量，并在后续生成的元数据加入示例动作说明；保留当时原始输出元数据不改写，语义测试对修改后的代码重新运行。

## 天玑右侧真实输入

`capture_once.py` 默认显示采集计划。执行采集时，系统 Python 复用 Argus 的 CSI0 头左、CSI5 右腕管线，预热后读取双图，并与一次右臂关节及右夹爪反馈读取得到主机侧时间窗。采集程序需要相机和 SDK，转换及回放仅使用已保存文件。

```bash
cd /home/nvidia/cph_dev/pi05
sample=offline-replay/evidence/real-right-20261112_144023_243023462
envs/openpi-sm87/bin/python offline-replay/pack_capture.py "$sample" "$sample/another-observation.npz"
LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu/nvidia \
 XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_FLAGS=--xla_gpu_autotune_level=4 \
 envs/openpi-sm87/bin/python -u offline-replay/replay.py "$sample/another-observation.npz" "$sample/another-replay"
```

转换保留两张原始 RGB8 图、B 侧七关节弧度、任务文本及原始采集/状态元数据。夹爪采用右侧已安装软件配置中的电机目标范围 0–1.6 rad，将反馈位置除以 1.6 并裁剪到 [0, 1]。这个比例表达电机位置，物理开口与 DROID 夹爪语义等价性待验证。主机取帧和 SDK 读取时间只描述主机侧采集，传感器曝光同步与夹爪反馈新鲜度仍未知。

## 天玑本机常驻推理

`pi05-inference.service` 由 nvidia 用户的 systemd 管理。服务从检查点加载策略，用上节保存的真实 NPZ 预热一次，输出通过有限值和 15×8 检查后，才在 `127.0.0.1:8000` 监听。预热和后续请求共用同一个 Policy。服务只接受观测和返回推理结果，不连接相机、SDK 或机械臂。

```bash
systemctl --user status pi05-inference.service
curl -f http://127.0.0.1:8000/healthz
journalctl _SYSTEMD_USER_UNIT=pi05-inference.service -n 30
```

从天玑本机发起一次请求：

```bash
cd /home/nvidia/cph_dev/pi05
envs/openpi-sm87/bin/python - <<'PYTHON'
import sys
sys.path.insert(0, "offline-replay")
from replay import load_observation
from openpi_client.websocket_client_policy import WebsocketClientPolicy

obs, _ = load_observation("offline-replay/evidence/real-right-20261112_144023_243023462/observation.npz")
client = WebsocketClientPolicy(host="127.0.0.1", port=8000)
result = client.infer(obs)
print(result["actions"].shape, result["server_timing"])
PYTHON
```

用 `systemctl --user stop pi05-inference.service` 停止并释放资源，或用 `start` 重新启动和预热。已为 nvidia 启用 linger，使服务在 SSH 退出后持续运行。该单元已链接，主机重启后需手动启动。预热用的真实 `observation.npz` 留在天玑。其他部署需提供兼容的 NPZ，并将服务的 `ExecStart` 改为对应路径。

## 实时双图与状态只读试跑

`live_bridge.py` 默认只打印计划。`--execute` 使用 CSI0 头左、CSI5 右腕及一次 SDK 只读会话，取得 B 侧七关节和右夹爪 0xCC 反馈。通过本机常驻推理服务连续请求，结果只保存为 `actions-*.npy`，同时写入时序、只读反馈与释放诊断。图像保留在内存中。夹爪 50 ms 未回包时重发同一状态刷新一次，400 ms 后仍无反馈则跳过该轮。

```bash
cd /home/nvidia/cph_dev/pi05
/usr/bin/python3 -u offline-replay/live_bridge.py --execute --duration 30 --out offline-replay/evidence/NEW_RUN
```

耗时从主机发起该轮采集到收到模型结果，传感器曝光时刻、源同步和夹爪反馈源新鲜度未确认。丢帧率和完成轮次延迟分别统计。试跑结束释放相机和 SDK，常驻服务继续运行。

## 已保存动作块的离线轨迹分析

```bash
cd /home/nvidia/cph_dev/pi05
/usr/bin/python3 offline-replay/review_action_trajectory.py --out offline-replay/evidence/NEW_ACTION_REVIEW
```

默认读取本次实时试跑和单帧真实回放，亦可用 `--live`、`--real` 指定对应证据目录。输出为名义运动学摘要及代表性关节、法兰和夹爪意图 CSV。右臂轴序和方向按同索引同符号假设，步长借用 DROID 参考。输入保持原始状态，超限轨迹仍保留用于诊断。本次安装配置对照在 `evidence/action-trajectory-review-20261112/independent-review.json`。

## Panda 和天玑的 FK 对比

```bash
cd /home/nvidia/cph_dev/pi05
/usr/bin/python3 offline-replay/compare_fk.py --out offline-replay/evidence/NEW_FK_REVIEW
```

脚本复算同序映射、固定有符号重排/缩放与单次线性末端重定向。Panda 几何来自 [DROID 33ae6a6 Panda MJCF](https://github.com/droid-dataset/droid/blob/33ae6a67274f36d2e29525b86f23a56616ef43a7/droid/robot_ik/franka/panda.xml) 的运动学节点；本地参考 XML 未带网格和纹理，脚本仅使用关节和法兰变换。新检出需从该固定版本链接下载 `panda.xml`，保存为 `offline-replay/reference/droid-panda-33ae6a6.xml`。天玑侧 FK 还依赖本机的运动学工具和已保存的观测。姿态敏感性及迭代数值对照在 `evidence/fk-comparison-20261112`，不构成实机映射或执行轨迹。
