# 2026-09-22 / R12b P9c失败/关闭回归固化

- 目标与范围：把P9c审阅时的五类retained、四代失败预算和close/completion并发检查固化；不修改生命周期实现，不纳入R13 artifact索引。
- 实现与验收：新增五态close资源守恒/匹配回收、四代失败占满预算与释放后新代history不受旧迟到事件污染，以及32 close+32 completion竞态测试；线程barrier/join有5秒超时并检查64个非daemon线程均结束。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | exit0；46/46通过 | Windows Python线程/RLock合成生命周期 |
| 64路close/completion竞态单测连续10次 | 10/10通过 | 调度采样，不是穷举 |
| `.venv\Scripts\python.exe -m py_compile tools\replay\lifecycle.py tests\replay\test_lifecycle.py` | exit0 | 语法检查 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；321 tests，263 pass / 58 skip | 能力缺失项保持skip |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium独立运行生命周期专测46/46并重复竞态10/10；确认两种close/completion线性化均可回收且不提交history，五态和四代断言完整，最终`APPROVE`，无剩余阻断。
- 未测/限制：非daemon worker若在生命周期内部永久死锁仍可能阻止Python退出；本批不证明真实后端quiescence/取消、进程级安全销毁、持久close回执或永久卡死恢复。不是完整FSR4、QNN/HTP、设备或游戏验证。
- 状态与下一步：R12b `complete`；下一叶R13，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
