# 2026-09-22 / R12a P9b有界幂等回归固化

- 目标与范围：把P9b审阅时的消费/reset并发、25+窗口和namespace独立检查固化；不修改生命周期实现，不纳入R12b的close/failure多代压力。
- 实现与验收：新增False消费的64路同值/冲突重试、reset的64路同参与32/32参数冲突、两个窗口分别跨32+记录且互不驱逐、过期通知不释放isolated资源，以及fresh context不继承旧进程内幂等记录的测试。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | exit0；43/43通过 | Windows线程级CPU合成生命周期 |
| `.venv\Scripts\python.exe -m py_compile tools\replay\lifecycle.py tests\replay\test_lifecycle.py` | exit0 | 语法检查 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；318 tests，260 pass / 58 skip | 能力缺失项保持skip |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium独立复跑生命周期专测43/43；初审指出新增并发测试可能无限等待，修复为5秒barrier/join并断言线程终止后复审`APPROVE`，无剩余阻断。
- 未测/限制：非daemon worker若在被测调用内永久死锁，join超时可报告断言但仍可能阻止Python进程退出，不能据此声称整进程有界。窗口淘汰后无法永久识别opaque ID；fresh context只证明内存记录不继承，不是实际进程重启持久性测试。没有稳定wire错误码、永久tombstone、完整FSR4、QNN/HTP、设备或游戏验证。
- 状态与下一步：R12a `complete`；下一叶R12b，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
