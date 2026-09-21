# 2026-09-22 / R08a 四venv聚合验证入口

- 目标与范围：基于`333ecf195ed9e6b03c62090c9ff2bc4f0ea5a6d0`新增显式baseline/reference/fsr-extract/QAIRT聚合入口；不创建环境、不安装依赖，也不把skip/not_run算作pass。
- 实现与验收：标准库协调器按固定顺序调用四个显式且互异的venv；内部worker直接读取`unittest`结果，父测试唯一分类且单列subtest事件。输出流落临时文件，hash/tail只覆盖收集开始时的固定大小快照。缺环境记`not_run`并继续（总exit2），测试/超时/结果畸形记`failed`并继续（总exit1），四组完成且无失败为exit0，即使仍有skip。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅实际`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.host.test_verify_environments -v` | exit0；16/16通过 | 聚合合同/故障注入，含subtest、fixture事件及输出快照回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；284 tests，236 pass / 48 skip | Windows host基线；四venv执行再次覆盖同一基线 |
| `.venv\Scripts\python.exe tools\host\verify_environments.py --baseline-python .venv\Scripts\python.exe --reference-python local\venvs\reference\Scripts\python.exe --fsr-python local\venvs\fsr-extract\Scripts\python.exe --qairt-python local\venvs\qairt-2.49.0.260730\Scripts\python.exe --output artifacts\r08a-multi-venv-20260922-final.json` | exit0；4 completed；399 observations=351 pass+48 skip | baseline 284、reference 13、fsr 24、QAIRT 78；存在跨组重叠 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现subtest重复事件误计数和超时后输出追赶风险；首次复审又发现`setUpClass`等fixture合成事件未分离。已改为已启动父测试唯一分类、subtest/fixture事件单列、全事件判定成败与固定大小输出快照，并补回归；最终复审`APPROVE`，无剩余阻断。
- 未测/限制：未在真实缺环境主机演练not_run；timeout不证明后代静止，快照后的后代输出不纳入hash/tail。不是HTP、设备、完整FSR4或游戏验证。
- 状态与下一步：R08a `complete`；下一叶R08b，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
