# 2026-09-22 / R11 P9a资源预算回归固化

- 目标与范围：把P9a审阅时的附加只读检查固化为确定性回归；不修改生命周期实现，不提前纳入R12a/R12b的幂等或close并发压力。
- 实现与验收：新增active/isolated各四种retained状态及六元错误身份不回收、大整数仍按逻辑cell计量、active+isolated恰到容量边界与超限原子拒绝、四个永久在途对象持续保持count背压的自动测试。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | exit0；38/38通过 | Windows CPU合成生命周期 |
| `.venv\Scripts\python.exe -m py_compile tools\replay\lifecycle.py tests\replay\test_lifecycle.py` | exit0 | 语法检查 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；313 tests，255 pass / 58 skip | 能力缺失项保持skip |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium独立复跑生命周期专测38/38；确认八类retained状态、六字段错误身份、大整数逻辑cell、4032+4160=8192边界/超限和连续16次永久背压断言均符合合同且未越入R12，最终`APPROVE`，无剩余阻断。
- 未测/限制：逻辑cell不是实际RAM/VRAM/DSP字节；永久不完成的工作按合同持续背压，本批不提供恢复/取消策略。不是完整FSR4、QNN/HTP、设备或游戏验证。
- 状态与下一步：R11 `complete`；下一叶R12a，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
