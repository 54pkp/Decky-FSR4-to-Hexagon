# 2026-09-22 / F01 pass1–13 CPU参考清单

- 基线与目标：基于`c4272669ccfcc1e5a0f47915fbb51e5081e0b825`建立pass1–13机器可验证清单，绑定current P7/P8、weights、graph与simulator；本批不实现任一pass。
- 实现：登记逐pass算子、primary/skip拓扑、固定8x8x16 signed-int8 HWC小输入、tensor/权重shape与布局、量化格式及call参数。严格区分graph WHCN、source weight KH/KW/Cin/Cout、CPU HWC/OIHW/IOHW；所有独立预期保持`unknown`。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；实现worker实际`gpt-5.6-sol / medium`；独立只读审计实际`gpt-5.6-sol / medium`；冻结diff由实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest tests.fsr.test_pass_manifest -v` | exit0；5/5通过 | 绑定此前验收的P7文件，并逐项核验清单所引用全部weight alias shape |
| `.venv\Scripts\python.exe -m unittest tests.fsr.test_pass_manifest -v` | exit0；4 pass / 1 skip | baseline无NumPy，skip准确 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests\fsr -p test_*.py` | exit0；49/49通过 | FSR主机工具回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；332 tests，271 pass / 61 skip | 能力缺失项保持skip |
| `.venv\Scripts\python.exe -m py_compile tools\fsr\pass_manifest.py tests\fsr\test_pass_manifest.py` | exit0 | 语法检查 |

- 审阅：Astra medium初审提出错误连边、权重删项、类型旁路和`.pyc`重读四类P2；固定完整拓扑/weight集合、严格类型、已哈希源码字节执行及P7 receipt outputs三方绑定后独立复跑专用环境5/5、baseline 4 pass/1 skip；记录边界修正后最终`APPROVE`，无剩余阻断。
- 未测/限制：固定材料不含`ml2code_runtime` operator HLSLI；zero-point、精确舍入/饱和/乘法次序只能标为unknown或pinned-simulator-derived。没有独立golden；8x8 fixture不是1080p或游戏输入。不是完整FSR4、ONNX、QNN/HTP、设备或游戏验证。
- 状态与下一步：F01 `complete`；下一叶F02a，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
