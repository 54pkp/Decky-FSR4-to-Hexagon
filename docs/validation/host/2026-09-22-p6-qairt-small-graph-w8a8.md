# 2026-09-22 / P6 QAIRT 小图 W8A8

- 目标与边界：基于 `b1fd2bd4cda4f720f0e6b42f98afe178e28feea1`，把 P5 `Conv -> Add -> ReLU` 小图实际转换、W8A8/B32 量化并用 QNN CPU 执行；协调/worker 为 GPT-5.6 Sol medium，实质审阅为 GPT-6 Astra medium。仅为 Windows 合成小图证据，不是 FSR4、HTP、设备或游戏验证。
- 环境：固定 QAIRT Community `2.49.0.260730`；管线使用独立 Python 3.12.14 QAIRT venv（NumPy 1.26.4、ONNX 1.18.0、protobuf 7.36.2、typing-extensions 4.14.0），P5 参考使用重建的独立 Python 3.12.14 venv（NumPy 2.2.6、ONNX 1.18.0、ONNX Runtime 1.22.0）。系统 Python 3.9.13 未修改。
- 实际结果：ONNX→float DLC→W8A8/B32 DLC、encoding JSON、`qairt-dlc-info` CSV 和 `QnnCpu.dll` 执行均成功。权重、激活和外部 I/O 实际为 per-tensor `uFxp_8`，bias 为 `sFxp_32`；这是 W8A8，不等同于 signed INT8。零值/图案/固定种子相对 P5 独立预期的最大绝对误差为 `0.0024145469`/`0.0056030303`/`0.0073367208`，均小于预声明 `atol=0.01, rtol=0`。
- 证据：本地忽略目录 `artifacts/P6-result-20260922-final/` 的 success receipt SHA-256 为 `01c2d64cfb96d6e1ff075eaee508a28b553e4f7b7269a0d1b920c34c432d03e3`；receipt 绑定 P3、SDK/工具、管线/参考源码、P5 模型与 raw、DLC、metadata、日志、CPU 输出和各自产物哈希。重复目标被拒绝，失败工作目录保留且不发布 success receipt。

| 检查 | 结果 |
| --- | --- |
| 实际固定 QAIRT 管线 | 退出 0；backend=`QNN_CPU`，3 个 case 数值门通过 |
| `local\venvs\qairt-2.49.0.260730\Scripts\python.exe -m unittest tests.qairt.test_small_graph_pipeline -v` | 退出 0；7 项通过 |
| `local\venvs\reference\Scripts\python.exe -m unittest discover -s tests/reference -p "test_*.py" -v` | 退出 0；11 项通过 |
| 两个独立 venv 的 `python -m pip check` | 均退出 0；无损坏依赖 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | 退出 0；233 项中 199 通过、34 skipped；7 项 P6 与 11 项 P5 因基线环境刻意不装 NumPy/ONNX 而跳过，其余为既有隔离数值环境或 Windows symlink 限制 |

- 失败与限制：首次转换因 QAIRT venv 缺 `onnx`，补入 ONNX 后又因缺 `protobuf` 失败，随后按上述精确版本补齐并通过；协调者第一次入口误用无 NumPy 的基线 `.venv`，README 已改为专用 QAIRT venv。converter 对当前图未使用的 `Inverse` 注册和 shape alias 发出 warning；未影响本图。HTP context/执行、FastRPC/CDSP、目标 SoC、signed INT8、per-channel/per-row、native uFxp I/O、Odin 3、FSR4 与游戏均 `not_run`。
- 下一步：P1–P9 主机队列至此完成；保持设备路线门槛，待连接 Odin 3 后再建立设备档案并单独验证 QNN/HTP、ABI、游戏、画质、性能与功耗。本轮到此停止。
