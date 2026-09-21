# 2026-09-21 / P5 自有小图 CPU 数值基准

- 目标与基线：基于 `b205ed645c6a56defbf0dfde2b232e8604ca8ce6`，增加自有小型 `Conv -> Add -> ReLU` ONNX 图、独立直接 NumPy 卷积预期和 Windows CPU 对照；变更限于 `tools/reference/`、`tests/reference/`、fixture 属性、STATUS 与本记录。
- 实现与产物：固定 `float32` 输入/输出 `reference_input`/`reference_output` 和 `[1,1,4,4]`，覆盖零值、字面图案、固定种子 `20260921` 非零输入；预先声明 `rtol=0`、`atol=1e-6`，锁定图节点、属性、初始化量、输入依赖和 `CPUExecutionProvider`。fixture SHA-256 为 `f89d2af81c2a9bbde23a7cf4b2a8ee2614535f491ab7f259ac3151328f4f42d4`。
- 环境与后端：Windows 11 AMD64；独立 `local/venvs/reference/`，Python 3.12.7、NumPy 2.2.6、ONNX 1.18.0、ONNX Runtime 1.22.0；实际推理后端仅 `CPUExecutionProvider`。协调/worker 为 GPT-5.6 Sol medium，批次审阅为 GPT-6 Astra medium。

| 检查 | 结果 |
| --- | --- |
| `local\venvs\reference\Scripts\python.exe -m unittest discover -s tests/reference -p "test_*.py" -v` | 退出 0；9 项通过 |
| `local\venvs\reference\Scripts\python.exe tools/reference/small_graph.py verify` | 退出 0；零值/图案/固定种子最大绝对误差为 `0`/`0`/`1.1920928955078125e-07` |
| `local\venvs\reference\Scripts\python.exe -m pip check` | 退出 0；无损坏依赖；`pip freeze` 与 12 项精确锁文件一致 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | 退出 0；153 项中 140 通过、13 skipped；其中 9 项因基线环境故意不安装 reference 依赖而跳过，另 4 项为既有 Windows symlink 权限限制 |

- 审阅：Astra medium 初审发现额外合法标量属性会触发未包装的 `TypeError`；已改为 protobuf 节点结构级精确比较并增加标量属性拒绝回归。Astra medium 对受影响实现、测试和 CPU verify 定点复核通过，无剩余 actionable finding。
- 未测/限制：没有 QAIRT/QNN、FSR4 权重、GPU、HTP、Odin 3 或游戏执行，设备与游戏均 `not_run`；CPU 小图结果不证明 FSR4 等价性、质量、性能或目标 ABI。可用 provider 列表含 Azure provider，但会话显式限制为 CPU，未运行 Azure provider。
- 下一步：P4 先实现合成 PE/ELF 只读解析和错误输入检查；缺 P3 合法 SDK 候选库时保持 `in_progress`，真实 ABI 清单与兼容性仍 unknown。本轮到此停止。
