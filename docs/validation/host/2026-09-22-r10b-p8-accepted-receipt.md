# 2026-09-22 / R10b P8 accepted receipt信任链

- 目标与范围：P8只消费R10a验收的P7 v2 receipt摘要，同时核对来源、提取器、环境/stdout gate和两项输出绑定；拒绝旧v1、wrapper/validated及仅内部自洽的替换收据。
- 实现与验收：公开合同固定P7 receipt SHA-256 `b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b`。消费者在读取artifact前核对固定摘要，并继续校验实际NPZ/graph哈希；测试合同可注入摘要以覆盖正负路径。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest tests.fsr.test_pass0_check -v` | exit0；18/18通过 | 包含旧schema、自洽伪v2及绑定缺失负例 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests\fsr -p test_*.py` | exit0；38/38通过 | FSR主机工具回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；309 tests，251 pass / 58 skip | NumPy P8用例因能力准确skip |
| `local\venvs\fsr-extract\Scripts\python.exe tools\fsr\pass0_check.py --p7-directory artifacts\p7-fsr-v07-r10a-20260922 --simulator research\fsr4-hexagon\model\sim\fsr4_sim.py --output artifacts\p8-pass0-r10b-20260922-coordinator-receipt.json` | exit0；0 LSB；P8 receipt SHA-256 `2a4c3960304dd19a2c00d70bcbe1309fad23b19017638250e15ce2263cbf8ede` | 复用忽略的固定P7材料；NumPy host CPU pass0 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium独立复跑P8专测18/18并核对真实P8 receipt摘要；确认固定摘要先于artifact读取、后续计算使用已验证字节快照，旧schema与自洽伪收据失败且不发布，最终`APPROVE`，无剩余阻断。
- 未测/限制：固定摘要会让任何合法重提取也先失败，更新须重新审计并显式修改合同。未重新下载或证明来源真实性；不是完整FSR4、ONNX、QNN/HTP、设备或游戏验证。
- 状态与下一步：R10b `complete`；下一叶R11，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
