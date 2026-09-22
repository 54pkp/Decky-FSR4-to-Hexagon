# 2026-09-22 / R13 当前artifact索引

- 目标与范围：建立版本化源码索引，按摘要区分accepted/current、historical/stale与audit-temporary；P8生产合同从固定索引选择current P7，不以目录名或CLI覆盖选择证据。
- 实现与验收：严格加载器拒绝重复JSON key、字段/类型/摘要错误、重复或歧义current，并要求current P8绑定current P7且为0-LSB。索引登记P7 `b791…d38b`与P8 `2a4c…f8ede`为current；旧`4170…`为绑定旧P7的历史0-LSB，`67e8…`为历史1-LSB，均不可冒充当前证据。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.fsr.test_artifact_index -v` | exit0；4/4通过 | stdlib索引合同，无NumPy依赖 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests\fsr -p test_*.py` | exit0；44/44通过 | FSR主机工具回归 |
| `local\venvs\fsr-extract\Scripts\python.exe tools\fsr\pass0_check.py --p7-directory artifacts\p7-fsr-v07-r10a-20260922 --simulator research\fsr4-hexagon\model\sim\fsr4_sim.py --output artifacts\p8-pass0-r13-20260922-coordinator-receipt.json` | exit0；0 LSB；摘要精确为current P8 `2a4c3960304dd19a2c00d70bcbe1309fad23b19017638250e15ce2263cbf8ede` | 复用忽略的固定P7材料；NumPy host CPU pass0 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；327 tests，267 pass / 60 skip | 能力缺失项保持skip |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审提出畸形类型泄漏、全量读取后限长及索引驱动测试不足三个P2；补齐字符串类型负例、`MAX+1`有界读取和隔离导入替代合法/无效索引测试后，独立复跑索引4/4与P8 20/20，最终`APPROVE`，无剩余阻断。
- 未测/限制：索引是源码内信任根，不包含忽略的大artifact；它分类既有证据，不重新证明来源真实性或数值正确性。未来current切换必须审阅索引与摘要；未列摘要一律untrusted。不是完整FSR4、ONNX、QNN/HTP、设备或游戏验证。
- 状态与下一步：R13及整个R队列`complete`；后续候选F01，本轮不继续。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
