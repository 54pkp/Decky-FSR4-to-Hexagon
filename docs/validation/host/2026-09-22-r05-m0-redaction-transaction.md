# 2026-09-22 / R05 M0公开脱敏整体事务

- 目标与范围：基于`03ce03822d95c1d2927317d9714bdc4f3e860604`将公开profile及evidence作为一个bundle事务发布；第二文件写入、完整校验或发布竞争失败均不暴露半成品。本批不改变脱敏语义，不证明POSIX或设备行为。
- 实现与验收：`output.parent`成为必须全新的bundle目录，其父目录必须已存在且非reparse。每次在同父随机私有staging写入全部文件，重读真实staged profile、核对预期内容并运行带文件校验，再用一次Windows目录`rename`发布。异常只清理本次staging。回归覆盖第二次写入失败、staged profile或evidence被破坏、竞争者先发布、既有输出拒绝和正常CLI往返；失败后final bundle不可见，赢家sentinel保留。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。
- 环境：Windows；基线`.venv` Python 3.12.14、jsonschema 4.26.0。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.device.test_profile_tools -v` | exit0；31/31通过 | Windows host_test；不证明POSIX rename |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；244项，206通过、38跳过 | 全仓基线；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现staged profile未被重读；修复为重读、核对预期对象后验证真实evidence，并增加损坏profile回归。聚焦复审`PASS`且独立复跑31/31，无剩余代码阻断项。
- 未测/限制：没有运行Linux/POSIX、Odin 3、HTP、FSR或游戏。目录级原子发布刻意不再支持写入既有output父目录；POSIX对已存在空目录的rename竞争语义未证明，保留设备计划。敌对进程替换私有staging仍不在正常发布者模型内。
- 状态与下一步：R05 `complete`；下一叶R06a，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
