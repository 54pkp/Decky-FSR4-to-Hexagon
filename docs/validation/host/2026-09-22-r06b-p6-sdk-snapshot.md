# 2026-09-22 / R06b P6固定SDK私有快照

- 目标与范围：基于`2f43b3c486ad63dc87b1795a92c4a12337c05b89`将P6执行从可变expanded SDK切换为固定官方ZIP派生的私有快照。本批只绑定SDK来源/文件闭包，不提前实现R06c的解释器、包清单和P3完整receipt绑定。
- 实现与验收：每次核验固定2.49.0.260730 ZIP并抽取三棵Windows runtime子树及`sdk.yaml`，以2,699文件、971,686,225 bytes、manifest SHA-256 `01f9e31813cc9c6c8111483e74cb9da231b3fcf7a4243e6d23238c722467f73d`作为保守执行闭包。QAIRT脚本、Python imports、PATH、QNN runner/backend/model均来自私有snapshot；每个SDK阶段前后复验全集，替换Python模块或额外native helper均拒绝。代表性`qti.*` import origin必须在snapshot manifest内；snapshot必须在success发布前清理成功。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe tools\qairt\small_graph_pipeline.py --archive downloads\qairt-community-2.49.0.260730.zip --qairt-python local\venvs\qairt-r06a-fresh\Scripts\python.exe --reference-python local\venvs\reference\Scripts\python.exe --model tools\reference\fixtures\conv_add_relu.onnx --work-root artifacts\P6-work-r06b-20260922 --output-root artifacts\P6-result-r06b-20260922 --p3-receipt artifacts\P3\qairt-2.49.0.260730-final-host-probe.json` | exit0；ONNX→DLC→W8A8/B32→metadata→QNN CPU；三例最大误差0.002415 / 0.005603 / 0.007337 | Windows固定snapshot合成小图/QNN CPU |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m unittest tests.qairt.test_environment tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline -v` | exit0；72/72通过，无skip | fresh QAIRT venv mock/fixture回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；260项，217通过、43跳过 | baseline；新增P6五项因未装NumPy/ONNX而随整类skip，skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现snapshot在发布后清理会造成“已发布但报错”，并发现P3 archive畸形类型可能泄漏异常。改为发布前严格清理、统一`PipelineError`并补cleanup失败不发布和畸形对象回归后，聚焦复审`PASS`且独立复跑14/14，无剩余阻断项。
- 未测/限制：闭包是可执行来源上界，不声称2,699文件全部实际加载；未密封Windows系统DLL、pip传递依赖或一次hash与load间的敌对主机竞态。异常清理仍可能留下未发布的临时snapshot供人工处理。没有运行HTP、Odin 3、完整FSR4或游戏。
- 状态与下一步：R06b `complete`；下一叶R06c，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
