# Orin π₀.₅ 部署参考方案评估

更新：2026-11-06。外部项目的测量未在天玑复现；本机 sm_87 结果见 [部署记录](README.zh-CN.md)。

| 方案 | 与本项目的联系 | 可借鉴内容 | 使用边界 |
| --- | --- | --- | --- |
| 当前采用 JAX sm_87 | AGX Orin 64GB；官方 pi05_droid；JAX0.5.3；Python3.11；输出15×8 | 本机PJRT补sm_87，autotune=4下算子和完整模型通过；30轮中位0.500秒、P95 0.507秒 | 同新环境autotune=0中位1.377秒；一次顺序对照，非长期稳定或天玑适配 |
| 保留 JAX 旧基线 | 相同模型及JAX版本；envs/openpi | 旧热轮1.238秒 | 关闭autotune；两轮结果留作回退，不与新结果宣称固定加速比 |
| ranpin/pi05-edge | AGX Orin 32GB、相同L4T/CUDA/JAX及openpi提交；官方pi05_libero | 编译与运行问题记录，预热后多轮计时、纯推理与通信时延分离、prefix/expert拆分、观测陈旧影响 | 同样关闭autotune；10×7的LIBERO结果不与DROID直接比较；其容器不等于当前环境 |
| CSDN PyTorch方案 | AGX Orin64GB、pi05_droid，转换官方checkpoint为Torch格式 | PyTorch GPU替代路径、保留归一化assets、先独立验证模型 | 2025年的Python3.10/Torch2.3组合及网盘包未采用；文章1.2秒不是本机对照实验 |

## 对当前工作的影响

1. pi05-edge 佐证当前 JAX0.5.3 + 关闭自动调优的可用绕过，未解决开启自动调优的 sm_87 兼容性，因此保留为旧基线；本机源码sm_87修复已完成开启autotune的算子和完整模型验收，当前采用独立新环境。暂不照搬其33.9GB容器、系统配置或依赖改动。
2. 用户此前选择保持Python3.11/Torch2.7.1、从官方源码针对sm_87构建；最新决定暂缓GPU Torch，先采用已验证的JAX GPU路线。保留源码和工具用于以后同条件速度比较，JAX结束后不自动触发Torch编译。
3. PyTorch首轮模型采用官方支持的 eager CUDA模式：在模型构造前通过配置令 pytorch_compile_mode=None。当前官方源码明确支持该路径，无需用 suppress_errors=True 隐藏编译回退。
4. 所有数据仍使用现有官方pi05_droid checkpoint。转换得到的safetensors另存，核对assets/droid/norm_stats.json；不把转换成功等同完整策略可加载。
5. 两类模型均仅使用合成输入，不操作设备。LIBERO仿真成功率不能证明天玑抓取；减少去噪步数、异步预取等会改变行为，尚未采纳。
6. 不把发现GPU、GPU内存增加或安装成功作为实际GPU计算的替代证据。以真实算子及完整模型执行结果为准。

## 来源

- [pi05-edge README](https://github.com/ranpin/pi05-edge)
- [pi05-edge 测量方法与环境](https://github.com/ranpin/pi05-edge/blob/cb26a2839e9c0fa3ab5428d46e0a38bb15c3c829/docs/METHODOLOGY.md)
- [pi05-edge 问题记录](https://github.com/ranpin/pi05-edge/blob/cb26a2839e9c0fa3ab5428d46e0a38bb15c3c829/docs/PROBLEMS.md)
- [CSDN：Orin64GB部署pi0/pi0.5](https://blog.csdn.net/nenchoumi3119/article/details/154258492)
- [官方openpi PyTorch实现及compile开关](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/models_pytorch/pi0_pytorch.py)
- [官方openpi PyTorch转换脚本](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/convert_jax_model_to_pytorch.py)
- [NVIDIA Jetson PyTorch兼容表](https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform-release-notes/pytorch-jetson-rel.html)
- [PyTorch JetPack/Torch-TensorRT指南：Jetson AI Lab索引来源旁证](https://docs.pytorch.org/TensorRT/getting_started/jetpack.html)

## 我们的私有跟踪记录

- [JAX sm_87修复验证 #1](https://github.com/emmm-50/tianji-openpi/issues/1)
- [CUDA Torch2.7.1源码构建与π₀.₅验证 #2](https://github.com/emmm-50/tianji-openpi/issues/2)

用户选择只在自有私有仓库记录并链接上游，未向上游公开发帖，未推送源码、权重或环境。
