# 2026-09-22 / R06c P6环境收据与漂移拒绝

- 目标与范围：基于`70d9d9ca6f6c0f508d8a5b009060c695ee33c3ed`把P6 success receipt升级为v2，绑定QAIRT/reference两个Python环境及固定P3收据身份；R06b的SDK snapshot闭包保持不变。
- 实现与验收：两个环境均要求CPython 3.12.14 AMD64、所选解释器同一文件、直接pin全部匹配且`pip check`通过；记录解释器哈希、完整installed package排序清单及摘要，并在执行后逐字段重采比较。P3固定SHA-256为`6deb0d3b5da94d1786d91a07898f7a83ce1e85379d382dc7629ce4b1795150d1`，另核对其Python、33项vendor依赖及archive/runtime身份，发布前复验文件未变。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe tools\qairt\small_graph_pipeline.py --archive downloads\qairt-community-2.49.0.260730.zip --qairt-python local\venvs\qairt-r06a-fresh\Scripts\python.exe --reference-python local\venvs\reference\Scripts\python.exe --model tools\reference\fixtures\conv_add_relu.onnx --work-root artifacts\P6-work-r06c-isolated-20260922 --output-root artifacts\P6-result-r06c-isolated-20260922 --p3-receipt artifacts\P3\qairt-2.49.0.260730-final-host-probe.json` | exit0；v2 receipt；QAIRT 35 required/89 installed，reference 12 required/13 installed；三例误差0.002415 / 0.005603 / 0.007337 | Windows固定snapshot合成小图/QNN CPU；使用修复后的隔离环境 |
| `.\local\venvs\qairt-r06a-fresh\Scripts\python.exe -m unittest tests.qairt.test_environment tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline` | exit0；76/76通过，无skip | fresh QAIRT venv fixture/mock回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；264项，217通过、47跳过 | baseline；P6环境专测随缺NumPy/ONNX整类skip，skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现探针使用`-I`但实际阶段可继承`PYTHONHOME`/user-site。清除所有继承`PYTHON*`和venv路由，只显式恢复UTF-8、禁user-site/bytecode及QAIRT snapshot `PYTHONPATH`，reference加`-s`；补污染父环境回归并重跑真实流程后，聚焦复审`PASS`且独立专测18/18，无剩余阻断项。
- 未测/限制：完整installed清单用于本次前后漂移检测，不是传递wheel/hash锁；未密封Windows系统DLL、网络索引或一次检查与load间可恢复的敌对竞态。没有运行HTP、Odin 3、完整FSR4或游戏。
- 状态与下一步：R06c `complete`；下一叶R06d，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
