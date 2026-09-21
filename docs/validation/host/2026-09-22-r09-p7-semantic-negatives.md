# 2026-09-22 / R09 P7 graph/NPZ语义负例

- 目标与范围：基于`888b73b6973d01b101e6f403dc72c59b69122130`把P7已有graph/NPZ语义门固化为独立负例；不声称完整图语义、官方golden或运行等价。
- 实现与验收：每个子场景从其余合法的100-array NPZ与graph出发，单独扰动`preset`/`model`、三类graph count、99/101 arrays、pass0/scale的缺名、shape和dtype，以及object dtype；逐项核对稳定诊断且确认不发布。生产验证已满足合同，本批只补测试。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅待`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest tests.fsr.test_intake -v` | exit0；15/15通过 | 6个方法含14个独立语义负例 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests/fsr -p test_*.py` | exit0；30/30通过 | R09+P8 NumPy/CPU专用suite |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；301 tests，247 pass / 54 skip | 新6方法因无NumPy准确skip，不冒充pass |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium确认14个负例分别扰动目标门、缺名场景仍保持100 arrays，且NumPy skip仅覆盖新6个方法；最终复审`APPROVE`，无剩余阻断。
- 未测/限制：未重跑真实v07提取；fixture只证明声明的marker/count/array shape/dtype门。不是完整FSR4、QNN/HTP、设备或游戏验证。
- 状态与下一步：R09 `complete`；下一叶R10a，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
