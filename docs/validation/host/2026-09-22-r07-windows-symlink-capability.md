# 2026-09-22 / R07 Windows文件symlink能力探测

- 目标与范围：基于`ff8a9bd9b70285d2adec00abad5638797b0e18f3`移除`commands.json`逃逸回归的Windows无条件skip；只改测试能力判定，不改采集器生产行为。
- 实现与验收：用例在自身临时目录、同卷同ACL上实际调用普通文件`os.symlink(..., target_is_directory=False)`。成功时确认link并执行原`InputError`安全断言；失败才skip，理由保留异常类型、errno、winerror、strerror和文本。注入单测分别固定覆盖能力成功和不可用两条分支。本机真实probe成功，集成项实际pass而非skip。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.device.test_collect -v` | exit0；9/9通过、0 skip；真实symlink集成pass | 当前Windows主机权限/文件系统 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；268项，220通过、48跳过 | baseline；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium冻结diff审阅`PASS`，独立复跑9/9且0 skip；按审阅提醒同步修正STATUS中已由R06b/R06c关闭的历史欠账描述。
- 未测/限制：不可用真实主机分支由故障注入验证诊断，未在第二台受限Windows主机实跑；不证明POSIX symlink/hardlink竞态、设备或游戏。
- 状态与下一步：R07 `complete`；下一叶R08a，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
