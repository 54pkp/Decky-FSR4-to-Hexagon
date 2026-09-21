# Decky FSR4 to Hexagon

中文 | [English](README.en.md)

本项目研究在骁龙 Linux 掌机上由 Qualcomm Hexagon NPU 执行 FSR4 神经网络子图，并由 GPU 负责特征、时序、重建和回写。首个目标仍是 AYN Odin 3 / Snapdragon 8 Elite / Armada OS。

> 当前是 Windows 主机准备与离线验证项目，不是可用的超分产品。尚未连接 Odin 3，也没有完整 FSR4、HTP 执行、GPU 流水、游戏适配、部署工具或 Decky 插件。唯一权威的当前进度见 [STATUS](docs/STATUS.md)。

## 已有证据

- M0 主机侧设备档案 schema、Linux 只读采集器、离线校验/脱敏，以及合成数值和生命周期回放工具。
- 已在本地固定官方 QAIRT Community 2.49.0.260730 包及隔离环境；自有 `Conv -> Add -> ReLU` 小图已完成真实 W8A8/B32 转换、元数据检查和 Windows QNN CPU 对照。它不是 FSR4，目标 HTP 也未执行。
- 已核验五个公开 FSR v07 `i8_quality` 源文件并提取 100-array NPZ 与 graph spec。P8 仅把固定小样本的前置 `pass0` 卷积与独立 CPU 标量实现作了 0-LSB 对照；pass1–13、FSR ONNX/QDQ、DLC、v79 context、官方 golden、GPU/HTP 均未完成。
- 2026-09-22 审计基线命令运行 233 项：199 passed、34 skipped；三个专用环境补跑其中 33 项，另 1 项做了手工行为核查。不能把单条基线命令写成 233/233 自动通过。

本地 SDK、模型与生成物位于 Git 忽略目录，不随源码分发。固定资产摘要和每批证据见 STATUS 所链接的记录。

## Windows 快速检查

需要显式指定 Python 3.10+。在仓库根目录运行：

```powershell
$python = 'C:\Path With Spaces\Python312\python.exe'
& $python tools/host/environment.py check --python $python
& $python tools/host/environment.py init --python $python --venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

`init` 只创建全新的目标并尝试从固定 requirements 安装基线依赖；它不保证机器已有缓存或网络，也不会补齐 QAIRT、ONNX Runtime、NumPy 等专用环境。已有 `.venv` 不要再次初始化，可用其中的解释器运行只读 `check`。详见 [主机环境说明](tools/host/README.md)。

## 文档入口

- [文档地图](docs/README.md)
- [唯一当前状态](docs/STATUS.md)
- [无设备 R 修复、F 真实 FSR 离线与 E 工程候选](docs/roadmap/HOST_PREPARATION.md)
- [设备 D 批次](docs/roadmap/DEVICE_EXECUTION.md)
- [已闭合 H/P 批次](docs/roadmap/COMPLETED_HOST_BATCHES.md)
- [轻量协作规则](docs/ai/MULTI_AGENT_WORKFLOW.md)

## 当前操作警示

- P6 发布仍存在已复现的并发清理所有权缺陷；修复前不要让两个任务使用相同发布名，每次使用全新的独占目录。P5 的创建竞争已由 R01 修复并有确定性回归。
- M0 仍有路径检查后并发替换和脱敏失败遗留半成品风险；不要在不可信目录中运行，也不要把失败输出当作可发布档案。
- 所有会写产物的命令都应使用新路径；完成后按 receipt 重新核对输入/输出 SHA-256。设备、游戏、性能和画质结论必须保持 `not_run`。

## 上游与许可边界

主要研究参考为 [fsr4-hexagon](https://github.com/puzzled-pancake/fsr4-hexagon)、[rp6-npu-unlock](https://github.com/puzzled-pancake/rp6-npu-unlock) 和 [hexscale](https://github.com/drewano/hexscale)。上游实验不能替代本项目的设备与游戏验证。

本仓库许可证尚待确定。AMD 模型、Qualcomm SDK/runtime、固件、游戏文件和上游代码各自遵循原许可；本仓库不分发这些专有资产，也不是 AMD、Qualcomm、NVIDIA、Valve、AYN 或 Decky 的官方项目。
