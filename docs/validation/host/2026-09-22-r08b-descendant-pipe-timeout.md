# 2026-09-22 / R08b P3后代管道超时回归

- 目标与范围：基于`f560bc323a169aea51ab10fcb97f8eaeb8c8ab03`固化Windows上后代进程继承P3 stdout/stderr管道时的有界返回；不实现或声称任意进程树终止。
- 实现与验收：直接进程结束或超时被终止后，两个daemon捕获线程共用有界宽限；管道仍被后代持有时立即fail-closed，诊断直接进程状态、每条捕获状态及可能的后代持有者。即使直接进程exit0，捕获不完整也不报成功。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅待`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\qairt-2.49.0.260730\Scripts\python.exe -m unittest tests.qairt.test_probe -v` | exit0；17/17通过 | 含2个真实Windows后代继承管道回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；286 tests，238 pass / 48 skip | Windows host基线 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审要求消除50ms内未必建立后代的回归竞态；已增加ready/PID显式握手及stop/done有界清理，并以`ResourceWarning`升级为错误复跑。最终复审`APPROVE`，无剩余阻断。
- 未测/限制：未验证POSIX进程组/SIGALRM；未终止或证明后代静止；不是HTP、设备、完整FSR4或游戏验证。
- 状态与下一步：R08b `complete`；下一叶R08c，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
