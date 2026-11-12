# π0.5 DROID 的 PyTorch GPU 离线验证

2026-11-05 最新决定：**GPU Torch 暂缓**，先采用已验证的 JAX GPU 路线。源码和工具保留，当前不编译、不安装或转换权重。以下步骤只供后续恢复该方案时使用，JAX构建结束不自动触发。`build-wheel.sh` 从官方 PyTorch v2.7.1 构建 CUDA wheel，源码提交 `e2d141dbde55c2a4370fac5165b0561b6af4798b`；编译日志、临时文件和 wheel 均在本目录。该脚本尚未验证构建成功。原 CPU 环境、原模型权重和 openpi 源码不修改。

```bash
/home/nvidia/cph_dev/pi05/torch-cuda/build-wheel.sh
```

构建日志需确认 CUDA 和 cuDNN 开启。经主 Agent 交接后，只将产出的 wheel 安装到 `/home/nvidia/cph_dev/pi05/envs/openpi-sm87`，从源码目录外验证实际导入路径、CUDA 版本、GPU 及真实同步矩阵乘和卷积。具体成功结果以 evidence 为准。

## 官方 Transformers 补丁

openpi 要求 transformers 4.53.2 和随源码提供的替换文件。安装 wheel 后，在 `openpi-sm87` 里确认版本，再使用 `cp --remove-destination`，先删除目标文件链接后创建副本，避免改动可能存在的共享硬链接缓存。目标目录必须由该环境的 Python 解析，不能指向其他环境。

```bash
ROOT=/home/nvidia/cph_dev/pi05
PY="$ROOT/envs/openpi-sm87/bin/python"
"$PY" -c 'import transformers; print(transformers.__version__, transformers.__file__)'
TARGET=$("$PY" -c 'import pathlib, transformers; print(pathlib.Path(transformers.__file__).parent)')
cp -r --remove-destination "$ROOT/openpi/src/openpi/models_pytorch/transformers_replace/." "$TARGET/"
```

## 转换权重

使用原始 JAX checkpoint 和官方转换脚本，CPU 上读取 OCDBT，不调用 GPU JAX autotune。转换过程可能占用较多内存和磁盘。产物目录独立于原权重。

```bash
ROOT=/home/nvidia/cph_dev/pi05
WORK="$ROOT/torch-cuda"
PY="$ROOT/envs/openpi-sm87/bin/python"
mkdir -p "$WORK/weights/pi05_droid-pytorch" "$WORK/evidence"
cd "$WORK"
JAX_PLATFORMS=cpu OPENPI_DATA_HOME="$ROOT/cache/openpi" \
PYTHONPATH="$ROOT/openpi/src:$ROOT/openpi/packages/openpi-client/src" \
"$PY" "$ROOT/openpi/examples/convert_jax_model_to_pytorch.py" \
  --checkpoint_dir "$ROOT/weights/pi05_droid" --config_name pi05_droid \
  --output_path "$WORK/weights/pi05_droid-pytorch" --precision bfloat16
mkdir -p "$WORK/weights/pi05_droid-pytorch/assets/droid"
cp "$ROOT/weights/pi05_droid/assets/droid/norm_stats.json" \
   "$WORK/weights/pi05_droid-pytorch/assets/droid/norm_stats.json"
cmp "$ROOT/weights/pi05_droid/assets/droid/norm_stats.json" \
    "$WORK/weights/pi05_droid-pytorch/assets/droid/norm_stats.json"
```

当前官方脚本尝试从 checkpoint 的父目录寻找 assets，而此 checkpoint 的 assets 位于自身目录；上面显式复制并比较原始 DROID 归一化统计。

## 推理

```bash
cd /home/nvidia/cph_dev/pi05/torch-cuda
/home/nvidia/cph_dev/pi05/envs/openpi-sm87/bin/python run_offline_torch.py
```

入口采用与原 `run_offline.py` 相同的随机种子和官方 DROID 示例（包含外部和腕部两张随机 RGB 图），采用官方 policy 和相同变换顺序。使用 `cuda:0`、显式 eager（`pytorch_compile_mode=None`）和 10 步采样；同步计时，记录设备、参数 device/dtype、加载、首轮/热轮、RSS 和 CUDA 峰值。预期动作形状为 15×8 且数值有限；结果写入 `evidence/offline_torch_result.json`。推理使用合成观测，只证明软件链路，不证明真实机器人行为。

## 后续速度对照

恢复CUDA Torch后，可在同一Orin上对照JAX关闭/开启autotune与Torch CUDA eager。使用同一官方权重来源、相同观测和提示、10步采样及15×8动作长度；记录实际参数精度，分别计量加载和首轮编译，再预热后固定多轮测量同步墙钟时间的中位数、P95及内存。当前JAX热轮1.238秒来自两轮功能验证，尚非正式多轮性能对照；不预先承诺Torch更快。
