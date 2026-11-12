# JAX sm_87 最新状态：已安装且离线验收通过

2026-11-06：构建和完整离线功能验收均已完成，**无需轮询、重建或重复安装**。
采用新环境 `../envs/openpi-sm87` 与本目录 `run_offline.py`，显式 autotune=4，系统CUDA12.6/cuDNN9.3。旧环境及旧结果保留。
wheel及安装后的插件均确认35个sm_87 cubin；四个JAX组件同为0.5.3。同步GPU矩阵乘、卷积与官方pi05_droid两轮10步合成推理通过，exit=0；加载20.299s、首轮50.826s、热轮0.514s，输出float64(15,8)且finite。
证据在 `evidence/` 的 `cuobjdump-list.*`、`pjrt-install.*`、`gpu-smoke.*`、`offline-run.*`、`offline_result.json` 和主Agent `main-review.json`。
完整版本/运行命令、内存与适配边界见 [部署记录](../README.zh-CN.md)；接续范围见 [根交接](../HANDOFF.zh-CN.md)。GPU Torch继续暂缓。
后续同新环境两组各3预热+30计时已完成：autotune=4中位0.499802s/P95 0.507034s；autotune=0中位1.376856s/P95 1.393424s。全部66次输出通过，独立证据 `evidence/benchmark-autotune{4,0}.*` 及 `benchmark-main-review.json`，采用autotune=4。DSH对采样参数建议已采纳，多轮逻辑补审无须再改。
下面仅保留11月5日构建历史，历史的“尚未”或检查命令不代表当前待办。

---

# JAX sm_87 后台构建交接

2026-11-05：用户要求暂不等待或主动轮询，完成后由用户再通知。前台 build-4 不是持久后台任务，已停止该 client 并保留 Bazel 缓存；同一参数重启为 nohup 后台任务，wrapper PID 502956（已由 PID 1 收养）。

- 命令：`/home/nvidia/cph_dev/pi05/jax-sm87/tools/build-background.sh`
- PID 文件：`/home/nvidia/cph_dev/pi05/jax-sm87/evidence/build-background.pid`
- 日志：`/home/nvidia/cph_dev/pi05/jax-sm87/evidence/build-background.log`；前次保留 `build-1.log` 到 `build-4.log`。
- 退出码：`/home/nvidia/cph_dev/pi05/jax-sm87/evidence/build-background.exit`；完成后原子写入，0 为构建成功，非 0 为失败。文件不存在时检查 PID 与日志区分运行和异常退出。
- 构建目标 JAX 0.5.3 CUDA12 PJRT，sm_87，Clang18 + 系统 GCC11 toolchain，系统 CUDA/cuDNN staging，NCCL关闭，Bazel jobs=4，内存调度20GiB。新环境：`/home/nvidia/cph_dev/pi05/envs/openpi-sm87`。

用户再次要求后检查：

```bash
p=/home/nvidia/cph_dev/pi05/jax-sm87
ps -p "$(cat "$p/evidence/build-background.pid")" -o pid,ppid,stat,args
cat "$p/evidence/build-background.exit" 2>/dev/null
tail -40 "$p/evidence/build-background.log"
```

尚未进行：构建成功后确认 wheel 版本 0.5.3 和 PJRT 二进制 cuobjdump sm_87，仅在新环境 --no-deps 安装；显式 `XLA_FLAGS=--xla_gpu_autotune_level=4` 验证 GPU 同步矩阵乘和卷积，再用新 runner 进行原权重、官方合成输入 10 步首轮/热轮推理，结果写 evidence，记录日志、设备、shape、finite、内存和耗时。原环境及旧结果不修改。新 runner 使用独立 tokenizer 缓存，未默认禁用 autotune。用户最新决定暂缓 GPU Torch；保留源码和构建准备，JAX完成后不自动编译或换装Torch。以后可在同条件下对比JAX GPU与Torch GPU推理速度。已安排今天19:20（Asia/Shanghai）单次只读检查JAX后台结果并汇报；本次提醒不自动安装或验证模型。
