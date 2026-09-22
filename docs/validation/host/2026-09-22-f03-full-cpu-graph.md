# 2026-09-22 / F03 pass1–13完整CPU主图

- 基线与目标：基于`e8657c5801f4a99d728a92289923615598ab28eb`从F01公式生成的合成p1输入逐pass组装p1–13，并与独立贯穿的F02 scalar分段证据逐层交叉；保留p9←p5与p11←p2两条skip，未执行或消费P8/pass0输出。
- 实现与结果：主图生成不可变13层trace，逐层shape/dtype/scale位模式/数据/hash一致；p1–p12为0 LSB，p13 float16为0 ULP，终点摘要`56fd10a7…`。错误注入可按字段定位首个偏差及输入/skip摘要。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；实现worker和只读设计审计实际`gpt-5.6-sol / medium`；冻结diff交实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest tests.fsr.test_full_cpu_graph -v` | exit0；6/6通过 | 逐层交叉、首差定位、skip消费点、不可变trace与封闭合同 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests\fsr -p test_*.py` | exit0；81/81通过 | FSR主机工具回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；364 tests，271 pass / 93 skip | NumPy F03用例准确skip |
| `local\venvs\fsr-extract\Scripts\python.exe -m py_compile tools\fsr\full_cpu_graph.py tests\fsr\test_full_cpu_graph.py` | exit0 | 语法检查 |

- 审阅：实际GPT-6 Astra medium发现合成p1输入被误称pass0输出、NumPy只读标志可被重新开启两项P2；修正文义并改用immutable bytes backing与只读映射后复审`APPROVE`，无剩余阻断。
- 未测/限制：scalar证据是三个既有F02分段的组合，不是第四独立oracle；共享P7、extractor与simulator-derived语义。未执行或消费P8/pass0输出，固定8x8边界不是1080p；不是官方golden、完整temporal FSR4、GPU前后处理、ONNX、QNN/HTP、设备或游戏验证。
- 状态与下一步：F03 `complete`；下一叶F04a，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
