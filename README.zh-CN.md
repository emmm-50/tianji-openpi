# 天玑 π₀.₅ 离线推理部署记录

仓库包含天玑自有源码和部署文档。克隆后用 `git submodule update --init --recursive` 获取固定版本的上游 OpenPI。文中 `evidence/` 路径指向天玑现场归档。原始实测证据、推理预热样本、模型权重及运行和构建环境留在天玑。

更新：2026-11-06（Asia/Shanghai）。目标主机：`TianJi-Codex-huawei` / `vision`，Jetson AGX Orin 64 GB，aarch64。

## 结论

官方 `pi05_droid` 的完整权重和离线资产已在天玑，**采用新环境 `envs/openpi-sm87` 和入口 `jax-sm87/run_offline.py`**。本机编译的 JAX 0.5.3 PJRT 插件含 35 个 sm_87 cubin；主 Agent 也独立核验了安装后的实际插件。显式启用 `XLA_FLAGS=--xla_gpu_autotune_level=4` 后，同步 GPU 矩阵乘、卷积和完整模型推理成功；随后同环境autotune=4/0各3轮预热+30轮计时也全部通过，原 RepeatBufferKernel / cudaErrorNoKernelImageForDevice 故障在本次路径中已消除。

新环境只用本地 wheel、`--no-deps` 替换同版 PJRT，JAX / jaxlib / kernel plugin / PJRT 均为 0.5.3，使用系统 JetPack CUDA 12.6 / cuDNN 9.3。没有跳过版本检查。旧环境 `envs/openpi`、旧入口 `run_offline.py` 和 `cache/` 结果保留为关闭自动调优的回退基线。

本次为合成输入、10 个 flow-matching 采样步的离线验收；首次两轮及后续多轮 actions 均为 NumPy `float64 (15, 8)` 且全部有限。这不是持续性能、稳定性或天玑机器人适配验证。GPU Torch 继续暂缓；未操作机械臂、夹爪、相机、ROS/SDK控制或策略服务器，未改系统或网络，未提交或推送。bot 的 PI0 项目未建立代码、环境或权重副本。

## 本阶段：契约调查与最小离线回放（2026-11-06）

已完成静态契约调查和一次合成单帧回放，主 Agent 已独立审查新源码、复跑语义测试并核对保存的原始数组。没有找到可确认的完整真实同步录制，因此**没有完成真实天玑数据回放或物理动作映射**；没有生成天玑命令。

- 契约依据和未知项：[天玑契约](contract/TIANJI_CONTRACT.zh-CN.md)、[官方 DROID 契约](contract/DROID_CONTRACT.zh-CN.md)。资料区旧 ROS 参考、已安装 014 SDK 声明、历史 APEX 运行记录分别标注，不当作本次现场状态。DROID 上游速度输入有自身的增量缩放，不能当成 rad/s 或直接发送天玑位置接口。
- 入口、NPZ 字段与运行命令：[单帧离线回放](offline-replay/README.zh-CN.md)。复用原环境、权重、tokenizer 和官方 Policy 变换序列，仅一次模型调用，autotune=4、10 采样步，cuda:0 上得到有限 float64 (15,8)；原始和官方示例后处理数组分别保留。
- 独立证据：[main-review.json](offline-replay/evidence/main-review.json)、[主 Agent 语义测试](offline-replay/evidence/main-semantics.log) 与对应 `.exit`；模型原始证据在 `offline-replay/evidence/synthetic-result/`、`replay.log/.exit`。均未覆盖此前 sm_87 或测速证据。
- 下一步先确定单侧、控制链和相机视角，补有真实反馈、来源及逐流时间戳的最小同步样本；动作序列验证另需连续状态/命令记录。具体条件见天玑契约末节。DROID 到天玑的物理映射、反馈语义、同步精度和任务表现仍未验证。

本阶段未接设备、未启动 ROS/SDK 控制或策略服务器，未改系统/网络、提交或推送；GPU Torch 暂缓。新源码由主 Agent 审查，未外发 DSH。bot PI0 未建立源码副本，也未新建 worktree。

## 工作区与版本

所有开发资产在 `/home/nvidia/cph_dev/pi05`：

| 项目 | 位置或版本 |
| --- | --- |
| 官方源码 | `openpi/`，上游 `https://github.com/Physical-Intelligence/openpi` |
| 固定提交 | `215abfb217dbac7d5f1273282331b9b1866c0479`，浅 Git 检出，验收时工作区干净 |
| 采用环境 / 保留回退 | `envs/openpi-sm87/` / `envs/openpi/`，Python 3.11.18 |
| 环境管理工具 | `tools/bin/micromamba`，2.10.0，conda-forge 包；未初始化或修改全局 shell |
| JAX / jaxlib / CUDA plugin / PJRT | 均为 0.5.3；新环境 PJRT 从官方 `jax-v0.5.3` 源码定向 sm_87 构建，使用系统 CUDA 库 |
| 系统平台 | L4T 36.4.4，系统 Python 3.10.12 保持原状 |
| 系统 CUDA / cuDNN | toolkit 12.6.11 / cuDNN 9.3.0.75 |
| Flax / Orbax | 0.10.2 / 0.11.13 |
| Torch / Transformers | 2.7.1+cpu / 4.53.2；Torch 的 `version.cuda=None`，仅满足官方模块导入，模型由 JAX GPU 执行 |
| NumPy / ml-dtypes / tensorstore | 1.26.4 / 0.4.1 / 0.1.74 |
| numpydantic / pydantic | 1.6.9 / 2.11.5，与 NumPy <2 的上游约束兼容 |
| 采用离线入口 | `jax-sm87/run_offline.py`，显式 autotune=4；旧入口保留 |

PJRT 源码提交：`c8032a9904eeb2410995425f817929f507fe22d5`。wheel 为 `jax-sm87/wheels/jax_cuda12_pjrt-0.5.3-py3-none-manylinux2014_aarch64.whl`（62,711,805 字节），仅安装于新环境。构建与采用边界详见 [JAX 接续记录](jax-sm87/HANDOFF.md)。

这是已验证的**离线推理依赖子集**，不是完整训练、LeRobot、RLDS、TensorFlow 或机器人仿真环境。官方代码的模型、分词、数据变换和采样实现均未修改。

官方 `policy_config.create_trained_policy` 通过训练 checkpoint 模块导入 LeRobot 数据加载链。本入口直接复用官方 `config`、`restore_params`、`model.load`、`normalize.load`、`Policy` 和相同顺序的 transforms，绕开无关训练模块的导入；没有 stub、伪造模型输出或 monkey patch。

Miniforge 初次直连下载停在首个 1 MiB，未执行不完整安装器，后改用官方 micromamba 建环境。随后确认已有 bot 代理可用：天玑 `127.0.0.1:17890` 转发至 bot 代理；后续依赖安装仅在当前进程显式使用该代理，未修改服务、网络或全局代理配置。Miniconda 并非不兼容，也没有因代理问题而必须被排除。当前无需 Hugging Face 登录或 token。

## 权重与离线资产

选择官方 `gs://openpi-assets/checkpoints/pi05_droid`，理由是它是 π₀.₅ 的 DROID 微调推理模型，具备官方随机观测示例、匹配的归一化统计与现成动作输出变换，适合先验证模型加载和推理。官方 `pi05_base` 更适合作为后续微调起点；本次未额外下载 base、LIBERO 或训练数据。

- 权重目录：`weights/pi05_droid/`。
- 官方 GCS 清单共 20 个对象，合计 **12,429,488,598 字节**（12.43 GB / 11.58 GiB）。
- 2026-11-06 主 Agent 再次逐个对照已有官方对象清单，20 个文件大小全部一致，无残留 `.partial`；新环境已再次完整恢复 checkpoint 并推理。未重下权重或新增 SHA 校验清单。
- 包含 `params/` 和 `assets/droid/norm_stats.json`。
- tokenizer：旧入口 `cache/openpi/big_vision/paligemma_tokenizer.model`，新入口独立缓存 `jax-sm87/cache/openpi/big_vision/paligemma_tokenizer.model`，均来自官方 `gs://big_vision/paligemma_tokenizer.model`。
- 对象清单与下载结果：`evidence/weight_objects.json`、`evidence/weight_download_result.json`；日志 `evidence/weights_download.log`。
- 下载耗时约 547.1 秒。2026-11-04 下载前可用约 808 GB，验收后约 794 GB；当时 `pi05` 目录约 15 GiB。该历史容量不包含后续 JAX/Torch 源码与构建缓存，不能当当前磁盘占用。
- 用户已在本次对话明确同意官方仓库附带的 Gemma 条款，之后才开始权重下载与使用。

## 离线验证与实测

输入使用官方 `droid_policy.make_droid_example()`，固定 NumPy seed 0：两张随机 224×224×3 uint8 RGB 图，7 关节位置、1 夹爪位置和文本提示。没有任何设备输入。

### 初次两轮功能验收（原始记录保留）

| 项目 | 新环境 sm_87 / autotune=4 | 旧环境 / autotune=0 |
| --- | ---: | ---: |
| 模型恢复与策略构建 | 20.299 秒 | 18.423 秒 |
| 首轮完整推理（含 JIT；新环境还含自动调优） | 50.826 秒 | 12.984 秒 |
| 第二轮热推理 | 0.514 秒 | 1.238 秒 |
| 实际设备 | cuda:0 | cuda:0 |
| 两轮 actions | (15, 8)，float64，finite=true | (15, 8)，float64，finite=true |
| 进程峰值 RSS | 17,240,832 KiB，约 16.44 GiB | 约 15.85 GiB |
| JAX peak_bytes_in_use | 7,114,114,560 字节，约 6.63 GiB | 约 6.63 GiB |
| JAX peak_pool_bytes | 8,587,837,440 字节，约 8.00 GiB | 约 8.00 GiB |

新旧数据分别是两轮功能验收的实测，不是控制负载、频率和多轮分布后的正式性能对照。新环境的单次热轮更快，首轮耗时更长；不能据此保证固定加速比或持续延迟。

### 多轮同环境对照（2026-11-06）

用户要求多轮测试后，在同一 `envs/openpi-sm87`、同一官方权重/输入/10采样步下，先autotune=4、再autotune=0，各以新进程串行执行。每组3轮预热（首轮含编译），随后30轮计时；模型默认seed与固定合成观测相同，计时覆盖同步的完整Policy.infer，不计逐轮日志、有限值检查及内存统计。

| 指标 | autotune=4 | autotune=0 |
| --- | ---: | ---: |
| 计时轮数 | 30 | 30 |
| 均值 | 0.499787 秒 | 1.377983 秒 |
| 中位数 | 0.499802 秒 | 1.376856 秒 |
| P95（NumPy线性插值） | 0.507034 秒 | 1.393424 秒 |
| 最小—最大 | 0.488845—0.517684 秒 | 1.358942—1.394664 秒 |
| 模型加载 | 17.058 秒 | 15.828 秒 |
| 第1次预热（含编译） | 49.423 秒 | 13.099 秒 |

按中位数，本次autotune=4约快 **2.75倍**，耗时减少 **63.7%**。两组含预热共66次输出均为float64(15,8)且有限，exit均0，进程均已退出。
两组使用同版包、同一PJRT和系统CUDA/cuDNN来源；调优选择会导致实际加载的cuBLAS/cuDNN子组件集合不同，不能把“加载库集合完全相等”作为对比条件。未调整时钟/功耗模式，也未排除其他系统负载；仅一次顺序对照，不证明长期稳定或机器人闭环实时性。

重跑多轮时，在下文标准运行命令中加入 `--warmup-runs 3 --runs 30 --output /自选目录/结果.json`，输出目录需已存在，并分别显式设置autotune=4/0、串行运行。参数未提供时仍为1预热+1测量的两轮规模。每次推理调用及结果记录都绑定同一个 `num_steps=10`。

原始证据：`jax-sm87/evidence/benchmark-autotune4.json`、`benchmark-autotune0.json` 及各自 `.log/.exit`、`-summary.json`；`benchmark-load-before.log` 保存测试前只读负载快照，`benchmark-main-review.json` 保存主Agent独立重算。初次两轮 `offline_result.json` 保持原样。

Orin 使用统一内存，RSS 与 JAX 设备统计存在交叠，不能直接相加。外层耗时覆盖 `Policy.infer` 并通过返回的 NumPy 数组同步结果；官方 `policy_timing.infer_ms` 也原样保存，但不以它替代外层完整耗时。

完整模型内部 action_dim=32，当前 `pi05_droid` 配置 action_horizon=15，官方 `DroidOutputs` 提取前 8 维。官方旧机器人示例中仍有 10×8 断言，本次依据固定提交的实际模型配置与实测结果记录 15×8。输出 float64 来自现有官方后处理链，未自行改精度。

新证据在 `jax-sm87/evidence/`：

- `cuobjdump-list.log/.exit`：wheel 二进制含 35 个 sm_87 cubin。
- `pjrt-install.log/.exit`：本地 wheel 安装；`main-review.json` 记录精确包版本、路径、安装来源、权重尺寸及主 Agent 验收。
- `gpu-smoke.py/.json/.log/.exit`：autotune=4 下真实同步矩阵乘和卷积及预期数值。
- `offline-run.log/.exit`、`offline_result.json`：完整模型两轮结果、同步外层耗时、实际 flags、checkpoint、RSS/JAX 内存及进程 maps 的已加载库。
- `pip-freeze.txt`：新环境安装清单。清单含 conda 管理的包，不是已验证的一键重建方案。
- `build-background.log/.exit`：成功的 PJRT 构建。项目内 Clang wrapper 使用系统 GCC11，系统 CUDA/cuDNN 仅以工作区薄 staging 提供给构建，不改系统工具链。

模型进程实际加载 `/usr/local/cuda-12.6/targets/aarch64-linux/lib/` 的 cuBLAS/cuDART、`/usr/lib/aarch64-linux-gnu/` 的 cuDNN9.3、系统 `nvidia/libcuda.so.1.1` 和新环境的 `xla_cuda_plugin.so`。OpenCV 导入后会给该进程的 LD_LIBRARY_PATH 前置自身 lib64；已按实际 maps 核实上述 GPU 库仍来自系统，没有以环境变量字符串代替库加载证据。

旧基线证据仍在 `cache/`：`jax-gpu-test.log`（默认自动调优首错）、`jax-gpu-no-autotune.log`、`offline-run.log`、`offline_result.json` 及原环境清单。未覆盖旧结果。本次模型进程正常退出，完整 openpi 源码工作区仍干净。

## 在天玑重跑

使用明确的环境解释器，无需改 shell 或全局环境：

```bash
cd /home/nvidia/cph_dev/pi05
LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu/nvidia \
  XLA_PYTHON_CLIENT_PREALLOCATE=false \
  XLA_FLAGS=--xla_gpu_autotune_level=4 \
  envs/openpi-sm87/bin/python -u jax-sm87/run_offline.py
```

新入口不默认关闭自动调优；上面的命令显式启用标准 level 4。脚本仅对自身进程默认关闭预分配，使用工作区 tokenizer 缓存和 HF 离线变量，保留调用者已设置的同名值。无需 HF 登录或下载。结果写入 `jax-sm87/evidence/offline_result.json`，重跑会覆盖该入口上一次 JSON；如需保留多次结果应先另存。旧入口及其关闭 autotune 的默认值保留为回退。

## 距离接入天玑的缺口

此权重针对 DROID/Franka 单臂，不代表天玑已适配，更不证明可以直接抓取。按现有天玑文档只能确认以下待落实项，未把文档当设备实时状态：

1. **单臂与动作契约。** DROID 是单臂 7 关节速度加 1 夹爪位置，天玑有左右两侧；参考 MoveIt 桥向 `/control/joint_cmd_A|B` 发布 positions。需选定侧别与既有控制链，确认状态/动作的关节顺序、单位、参考系、速度或位置接口及执行时间，不能直接将 8 维输出发给天玑。
2. **相机与观测。** 需确定外部及腕部 RGB 相机、安装视角、标定、图像格式，以及图像和关节/夹爪状态的同步；本次未确认现场相机可用性。
3. **夹爪映射。** 现有文档的 `/tj/control/gripperValueL/R` 为 0..1，需核实实际开闭方向、行程、反馈与唯一命令来源，不能仅凭同为 0..1 判兼容。
4. **控制周期和推理时延。** 需定义动作块执行、重规划与状态同步。当前新环境30轮合成输入计时中位数约0.500秒、P95约0.507秒；尚未验证长时间延迟、观测陈旧影响或闭环抓取表现。
5. **天玑数据与泛化。** 需确认是否已有带任务文本的同步图像、状态、动作示教数据；很可能需要基于天玑数据适配或微调，DROID 的泛化表现不能视为天玑零样本成功保证。本阶段静态契约与合成回放已完成，见上文；真实同步数据回放及设备测试尚未进行。

相关本机文档：
- `/home/nvidia/cph_dev/robot_resources/tianji/research/marvin_pro_20261015/ros_README.md`
- `/home/nvidia/cph_dev/tianji_quest_nova/provenance/interface_audit.zh-CN.md`
- `/home/nvidia/cph_dev/tianji_quest_nova/README.md`

## 审查与官方来源

主 Agent 已独立对照官方 `policy_config.py`、`policy.py` 与 `pi0.py`：变换顺序一致，默认采样10步，Policy返回 NumPy 前同步；已独立读取安装后的实际插件架构、完整日志/结果、包版本、系统 GPU 库路径、权重大小与 Git 状态。用户明确授权限定源码发送至DeepSeek API后，DSH已完成只读审查：建议把10步同时绑定实际调用与记录；主Agent核实并采纳，未增门禁。新增多轮CLI及统计补审结论为无须进一步修改。两次最终审查结果归档在 `jax-sm87/evidence/dsh-review-1.json`、`dsh-review-2.json`。

私有 [JAX issue #1](https://github.com/emmm-50/tianji-openpi/issues/1) 已按完整离线目标通过更新并关闭为completed；[GPU Torch issue #2](https://github.com/emmm-50/tianji-openpi/issues/2) 继续暂缓。2026-11-06 查询时上游 [PR #40492](https://github.com/jax-ml/jax/pull/40492) 仍开放。本次为本机0.5.3定向构建，不宣称已使用上游发行修复或直接复现0.11.1同版问题。

- [官方 openpi README](https://github.com/Physical-Intelligence/openpi/tree/215abfb217dbac7d5f1273282331b9b1866c0479)
- [固定提交的模型与数据配置](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/config.py)
- [官方 DROID 动作接口示例](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/examples/droid/main.py)
- [Gemma 条款](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/LICENSE_GEMMA.txt)
- [JAX 0.5.3 固定版本安装说明](https://github.com/jax-ml/jax/blob/jax-v0.5.3/docs/installation.md)
- [相关 JAX Orin issue；外部个案，不替代本机实测](https://github.com/jax-ml/jax/issues/40487)
