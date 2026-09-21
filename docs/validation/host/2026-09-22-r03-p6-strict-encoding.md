# 2026-09-22 / R03 P6 encoding严格解析

- 目标与范围：基于`cbd994ff784f38344b65e202437b9f3b94835ce6`令P6 encoding解析fail-closed；拒绝非整数/错误类型bitwidth及非允许布尔表示，不改变scale/offset、转换或数值合同。
- 实现与验收：bitwidth仅接受非bool的JSON整数；symmetry仅接受原生JSON布尔或固定QAIRT 2.49实际输出的精确小写字符串`"true"`/`"false"`。回归拒绝8.5、8.0、字符串、bool/null bitwidth，以及null、数值、大小写/空白/任意字符串symmetry，并覆盖false/true tensor；固定SDK字符串和原生bool成功路径保留。本机既有固定P6产物`artifacts/P6-result-20260922-final/small_graph.w8a8_encoding.json`（ignored）逐项观察到整数bitwidth和精确小写字符串，提交中的fixture锁定同一格式。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。
- 环境：Windows；QAIRT隔离解释器Python 3.12.14、NumPy 1.26.4。fixture模拟固定SDK元数据，不执行真实转换或后端。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\qairt-2.49.0.260730\Scripts\python.exe -m unittest tests.qairt.test_small_graph_pipeline -v` | exit0；9/9通过 | Windows host_test；含严格类型矩阵 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；237项，199通过、38跳过；QAIRT项因基线环境无NumPy按设计skip | 基线；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：`gpt-6-astra / medium`审冻结diff、核对固定P6 encoding格式并独立复跑专测9/9；按反馈补原生True成功回归、收窄README结论后最终`pass`，无待修问题。
- 未测/限制：没有重跑真实SDK、QNN CPU、HTP、设备、FSR或游戏。其它QAIRT版本若输出大小写或空白字符串将被刻意拒绝，需先经独立版本适配；字段别名冲突和scale/offset策略不在R03。
- 状态与下一步：R03 `complete`；下一叶R04处理M0 evidence TOCTOU，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
