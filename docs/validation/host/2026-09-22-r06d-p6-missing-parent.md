# 2026-09-22 / R06d P6缺失父目录诊断

- 目标与范围：基于`d4f6cfdd262b64ad250a1cd94584c75fc935bf53`规范P6 work/output直接父目录缺失的失败语义；不改变转换、量化、receipt或正常发布行为。
- 实现与验收：`_safe_new_root`把缺父及祖先stat错误统一转为带root标签的`PipelineError`，拒绝dangling占用，并返回已验证父目录identity供output复用，消除紧邻的第二次裸stat窗口。CLI稳定exit1、stderr单行诊断、stdout空且无traceback；不自动创建父目录。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m unittest tests.qairt.test_small_graph_pipeline -v` | exit0；20/20通过 | work/output缺父直接调用及CLI负例、正常fixture |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m unittest tests.qairt.test_environment tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline` | exit0；78/78通过，无skip | fresh QAIRT venv focused回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；266项，217通过、49跳过 | baseline；P6专测随缺NumPy/ONNX整类skip，skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium冻结diff审阅`PASS`，独立复跑新增两项2/2通过；缺父/祖先异常、父identity复用、既有占用和reparse语义无阻断项。
- 未测/限制：不证明任意I/O错误可恢复，也不关闭预检后的所有敌对文件系统竞态；没有运行HTP、Odin 3、完整FSR4或游戏。
- 状态与下一步：R06d `complete`；下一叶R07，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
