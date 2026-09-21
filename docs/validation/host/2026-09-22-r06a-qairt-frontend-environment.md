# 2026-09-22 / R06a QAIRT/P6前端环境重建

- 目标与范围：基于`bf7eba5f208bab9d522d06a22e81d8e02a2381fc`固化Windows QAIRT/P6 Python前端配方。新增35条精确直接依赖（P3固定的33项vendor要求，加ONNX 1.18.0、protobuf 7.36.2）和专用初始化入口；不改P6执行、SDK绑定或receipt合同。
- 实现与验收：入口只接受显式CPython 3.12.14 AMD64和全新目标，用隔离pip创建、安装、`pip check`并回读核对35个版本；失败保留partial venv且不覆盖已有路径。以新建忽略目录`local/venvs/qairt-r06a-fresh`实际重建，P6测试在该环境实跑而非skip。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。
- 边界：锁定的是35个直接依赖，不是传递wheel/hash或native SDK闭包；SDK/ZIP仍是本机忽略资产且本批未下载、转换或执行真实模型。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe tools\qairt\environment.py init --python .venv\Scripts\python.exe --venv local\venvs\qairt-r06a-fresh` | exit0；CPython 3.12.14 AMD64；35个pin回读匹配 | fresh Windows venv；使用网络索引解析传递依赖 |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m pip --isolated check` | exit0；无损坏依赖 | 仅Python包依赖 |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m unittest tests.qairt.test_environment tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline -v` | exit0；67/67通过，P6九项均实跑 | fixture/mock/CPU Python测试，不是QAIRT工具转换复跑 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；255项，217通过、38跳过 | baseline；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审要求测试兼容非目标baseline、核验CPython implementation并展开完整命令；聚焦复审又纠正Windows ARM64能力判断。全部修复后最终复审`PASS`，无剩余阻断项。
- 未测/限制：没有证明传递依赖可长期从索引重现、SDK/native文件闭包、真实QAIRT转换、QNN CPU再次执行、HTP、Odin 3、FSR4或游戏。
- 状态与下一步：R06a `complete`；下一叶R06b，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
