# Tianji OpenPI

面向天玑双臂机器人的 π₀.₅ 视觉语言动作模型（VLA）开发与接入项目，基于 [Physical Intelligence OpenPI](https://github.com/Physical-Intelligence/openpi)。仓库围绕模型推理、机器人数据、运动学和 APEX VLA Host 通信组织代码与文档。

## 项目内容

- **模型与数据**：π₀.₅ 推理适配、机器人观测处理、微调配置和动作归一化。
- **动作与运动学**：关节空间动作、末端位姿表示，以及 FK / IK 计算工具。
- **机器人接入**：相机与状态读取、APEX VLA Host 客户端和关节指令传递。
- **开发与分析**：录制数据回放、离线分析、接口 mock 和部署环境说明。

## 代码目录

| 目录 | 内容 |
| --- | --- |
| [openpi/](openpi/) | 上游 OpenPI 子模块 |
| [tianji-lora/](https://github.com/emmm-50/tianji-openpi/tree/codex/pi05-handoff-20261120/tianji-lora) | 天玑模型适配、微调配置与 VLA Host 客户端 |
| [eef-control/](https://github.com/emmm-50/tianji-openpi/tree/codex/pi05-handoff-20261120/eef-control) | 原始模型输出采样、末端运动学与接口测试工具 |
| [offline-replay/](offline-replay/) | 观测采集、动作回放、重定向与分析 |
| [contract/](contract/) | 机器人、数据和控制接口约定 |
| [jax-sm87/](jax-sm87/) | Jetson Orin 的 JAX 运行环境与相关说明 |

项目以天玑机器上的部署环境为主要运行环境。Git 仓库保存源码与说明；模型权重、数据集、Python 环境和实验产物在部署环境中管理。

## 文档导航

- [机器人接入与操作说明](https://github.com/emmm-50/tianji-openpi/blob/codex/pi05-handoff-20261120/eef-control/HANDOFF.zh-CN.md)
- [末端控制模块说明](https://github.com/emmm-50/tianji-openpi/blob/codex/pi05-handoff-20261120/eef-control/README.zh-CN.md)
- [采集、回放与分析](offline-replay/README.zh-CN.md)
- [天玑接口约定](contract/TIANJI_CONTRACT.zh-CN.md)
- [DROID 接口约定](contract/DROID_CONTRACT.zh-CN.md)
- [部署环境参考](reference-deployment.zh-CN.md)

## 上游项目

模型实现来自 [Physical Intelligence / OpenPI](https://github.com/Physical-Intelligence/openpi)，通过 Git 子模块管理。相关代码与模型的使用条款见上游仓库及其模型说明。
