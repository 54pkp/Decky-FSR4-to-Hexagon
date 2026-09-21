# 2026-09-22 / R02 P6私有发布staging

- 目标与范围：基于`b82cc65f665ed5818ad3b65f65de63fe85dc2761`修复P6共享`.publishing`目录的双发布者竞争。每次发布独占同父随机staging，败者只能清理本次目录；不改变转换、量化或数值合同。
- 实现与验收：使用`tempfile.mkdtemp`创建私有staging，在其中复制work并写success receipt，最后以`os.replace`竞争目标。确定性重入测试让两个独立work共享output，第二发布者先完成真实rename，随后第一发布者真实rename失败；两个staging名称不同，赢家完整文件/receipt字节不变，败者staging清理且未公开receipt，无关目录sentinel保留。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。
- 环境：Windows；QAIRT隔离解释器Python 3.12.14、NumPy 1.26.4。测试使用自有fixture/mock发布调度，不执行真实QAIRT工具或QNN后端。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\qairt-2.49.0.260730\Scripts\python.exe -m unittest tests.qairt.test_small_graph_pipeline -v` | exit0；8/8通过 | Windows host_test；含确定性双发布者重入 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；236项，199通过、37跳过；QAIRT专测因基线环境无NumPy而按设计skip | 基线；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：`gpt-6-astra / medium`初审要求把手造赢家改为两个完整Fixture的确定性重入并核对两个私有staging；修复后审冻结diff并独立复跑专测8/8，最终`pass`，无待修问题。
- 未测/限制：没有运行真实SDK转换、QNN CPU、HTP、设备、FSR或游戏。mock证明Windows发布临界点语义，不证明跨平台rename；敌对进程替换已创建的私有staging或父目录仍超出R02正常发布者竞争范围。
- 状态与下一步：R02 `complete`；下一叶为R03严格encoding解析，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准，不含SDK、venv、模型或ignored产物。
