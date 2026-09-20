# Decky FSR4 to Hexagon

中文 | [English](README.en.md)

本项目探索在骁龙 Linux 掌机上，让 **Qualcomm Hexagon NPU 执行 FSR4 神经网络推理**，并由 GPU 完成特征准备、时序处理、重建与回写。首个研究目标是 **AYN Odin 3 / Snapdragon 8 Elite / Armada OS**，计划从游戏的 DLSS Super Resolution 接口接入，后续再评估 Steam 与可选 Decky 管理界面。

> **当前阶段：仅有 M0 主机工具与设计文档，没有超分运行时。**
> 尚未连接或测试 Odin 3；当前证据仅来自 Windows、匿名 fixture、离线检查和 CPU 主机测试。仓库没有可安装插件、已验证游戏、HTP/QNN NPU 执行结果或性能数据，不能声称 FSR4 已在 Hexagon NPU 上可用。

## 已有内容

- `draft-0` 设备档案 schema。
- Linux 普通用户只读采集器 `tools/device/collect.py`；它不安装软件、提权、改固件、解锁硬件或打开 DSP 会话。
- 离线档案校验与公开脱敏工具 `tools/device/profile_tools.py`。
- 匿名 fixture 与 Windows 可运行的 Python 回归测试。

这些工具用于建立设备事实和验证文件处理边界，不包含 FSR4 模型执行、GPU/NPU 图形链路、游戏接入、启动器或 Decky 插件。NPU 也只会承担完整超分算法的一部分。

## Windows 主机检查

需要 Python 3.10+。在仓库根目录运行：

```powershell
python -m pip install -r tools/device/requirements-host.txt
python -m unittest discover -s tests/device -v
```

该检查无需设备，只验证 Python 工具和 fixture 行为；它不是 Odin 3、CDSP/FastRPC、HTP、FSR4 或游戏验证。实时设备采集仅支持 Linux，使用方法见 [`tools/device/README.md`](tools/device/README.md)。

## 开发入口

- [当前状态与工作队列](docs/STATUS.md)
- [轻量协作规则](docs/ai/MULTI_AGENT_WORKFLOW.md)
- [单次执行提示词](docs/ai/SINGLE_RUN_PROMPT.md)
- [可续跑 Goal 提示词](docs/ai/GOAL_PROMPT.md)

需要实现某个节点时，再查阅[详细路线与研究资料入口](docs/roadmap/README.md)。所有结论必须区分源码审阅、编译、主机测试、设备测试和游戏测试。

## 上游与许可边界

- [fsr4-hexagon](https://github.com/puzzled-pancake/fsr4-hexagon)：FSR4/Hexagon 实验与模型移植研究。
- [rp6-npu-unlock](https://github.com/puzzled-pancake/rp6-npu-unlock)：特定 RP6 平台的 NPU 研究，不是 Odin 3 安装步骤。
- [drewano/hexscale](https://github.com/drewano/hexscale)：Vulkan、QNN 服务与诊断参考。
- [54pkp/hexscale](https://github.com/54pkp/hexscale)：相关 QNN/管理工具参考。

本仓库许可证尚待确定。AMD 模型、Qualcomm SDK/runtime、固件、游戏文件和上游代码各自遵循原许可；本仓库不分发这些专有资产，也不是 AMD、Qualcomm、NVIDIA、Valve、AYN 或 Decky 的官方项目。上游实验不能替代本项目的设备与游戏验证。
