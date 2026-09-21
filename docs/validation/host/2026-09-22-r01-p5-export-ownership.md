# 2026-09-22 / R01 P5导出目录所有权修复

- 目标与范围：基于`e7fb7f8a35657f9e7dad38a8cf4c01145c409be4`关闭P5 `export_calibration` 的check→mkdir竞争；只有本次成功独占创建目录后，失败路径才允许清理。本批不改P6、不证明ONNX数值、FSR4、HTP、设备或游戏行为。
- 实现：将输出目录所有权初始化为false，`mkdir`成功后才置true；创建竞争产生的`FileExistsError`转为稳定`ReferenceError`，未取得所有权时不调用`rmtree`。确定性注入让竞争者先建立同名目录与sentinel，再触发创建失败；另注入写失败确认本任务自有目录仍会清理，既有成功导出回归保持通过。
- 实际角色：协调者当前会话的型号/强度没有可独立核验回执，记`unknown`；只读worker通过实际参数使用`gpt-5.6-sol / medium`；冻结diff由`gpt-6-astra / medium`审阅，结论见下。
- 环境：Windows；专用reference解释器为Python 3.12.14、NumPy 2.2.6、ONNX 1.18.0、ONNX Runtime 1.22.0。基线`.venv`为Python 3.12.14且刻意不含NumPy/ONNX。

## 检查

| 命令 | 结果 | 证据边界 |
| --- | --- | --- |
| `local\venvs\reference\Scripts\python.exe -m unittest tests.reference.test_small_graph -v` | exit0；13/13通过，包含竞争保留、失败清理和串行成功 | Windows host_test；不是FSR4或设备证据 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；235项，199通过、36跳过；新增2项因基线环境无NumPy/ONNX而按设计跳过 | 基线回归；skipped不算pass |
| `local\venvs\reference\Scripts\python.exe tools/reference/small_graph.py verify` | exit0；CPUExecutionProvider三例最大绝对误差0 / 0 / 1.1920928955078125e-07，模型SHA-256 `f89d2af81c2a9bbde23a7cf4b2a8ee2614535f491ab7f259ac3151328f4f42d4` | 仅自有小图CPU |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：`gpt-6-astra / medium`审当前冻结diff、全部新增记录及状态/README同步，结论`pass`，无可操作问题；确认竞争注入在旧实现确定失败、异常边界保持兼容。审阅未独立复跑数值/基线命令，采用协调者的实际运行证据。
- 未测/限制：没有运行QAIRT、HTP、Odin 3或游戏。布尔所有权关闭的是已复现的创建失败误删；若外部进程在本任务成功创建后主动删除并替换同名目录，路径式清理仍可能作用于替换对象，该敌对替换需要目录身份或私有staging策略，超出R01验收。
- 状态同步：R01 `complete`；下一步R02修复P6发布竞争。本轮不继续R02。
- Git交付：协调者已核对origin、main分支及作者`54pkp <67623881+54pkp@users.noreply.github.com>`；仅暂存R01实现、测试和同步文档。本记录随本批提交，实际提交/正常推送结果以Git历史与任务最终回复为准；不含本地venv、SDK、模型或ignored产物。
