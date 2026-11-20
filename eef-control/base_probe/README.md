# π₀.₅ base 离线原始输出采样

入口使用本机 base 权重、`Pi0Config(pi05=True)` 默认 50×32、bfloat16 恢复，记录 plain / world_eef / wrist_eef 三组原始归一化输出及相同固定噪声。它把 DROID 输入变换与 base 自带 DROID 状态统计作为实验假设；它们尚未证明适配天玑。末端前缀来自 π₀ 作者讨论，是否适用 π₀.₅ 未知，而且现有 tokenizer 会将前缀中的下划线替换为空格。输出差异不能证明成功切换动作模式；当前尚未对齐末端通道、姿态编码、坐标系和反归一化；此入口输出的是原始数值，末端解码是后续接力接口。

天玑离线运行（示例目录须不存在）：

```bash
cd /home/nvidia/cph_dev/pi05
mkdir /tmp/pi05-base-output
LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu/nvidia \
XLA_FLAGS=--xla_gpu_autotune_level=4 XLA_PYTHON_CLIENT_PREALLOCATE=false \
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
envs/openpi-sm87/bin/python -u eef-control/base_probe/run.py --output-dir /tmp/pi05-base-output
```

默认读取历史录制图片及关节/夹爪观测；通过 `--checkpoint` 和 `--observation` 可指定其他路径。输出目录须已存在且不含 `base-probe.json`、`base-probe.npz`，防止覆盖现有结果。NPZ 包含 `plain`、`world_eef`、`wrist_eef` 和 `noise`。默认录制数据不同步、夹爪及视觉物理映射未验证。清理示例输出使用 `rm -rf /tmp/pi05-base-output`；需保留的实验结果应先由使用者另行保存。

2026-11-20 既有实际结果为 `evidence/base-eef-ik-20261119/base-actual-20261120.json/.npz`；本入口整理后已实际运行 GPU 回归，三组 50×32 输出均有限，结果在 `evidence/handoff-20261120/base-probe/`。
