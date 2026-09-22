# 2026-09-22 / F04a真实p3最小ONNX分段

- 基线与目标：基于`3f66020fb1660422e22c9d042c939aae5fb82fc7`从认证P7权重/偏置确定性导出真实p3下采样段；静态NCHW int8边界，经input/weight DQ、2x2 stride-2 Conv+bias及axis=1输出Q。
- 实现与结果：固定tensor/QDQ/来源/initializer/图合同；模型3,251 bytes，SHA-256 `2f15dce7ecabf990573f2a1794d984ee62950cdcbcba6a0764c77949390c0448`，重复构建一致且`onnx.checker`通过。模型嵌入真实权重，仅在ignored路径重建，不随源码提交。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；实现worker和只读设计审计实际`gpt-5.6-sol / medium`；冻结diff交实际`gpt-6-astra / medium`审阅。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\reference\Scripts\python.exe -m unittest tests.fsr.test_onnx_segment_p3 -v` | exit0；9/9通过 | 确定性构建、checker、固定manifest快照认证、真实CLI、独占发布与结构负例 |
| `local\venvs\reference\Scripts\python.exe -m unittest discover -s tests\fsr -p test_*.py` | exit0；90/90通过 | reference环境FSR回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；373 tests，271 pass / 102 skip | ONNX/NumPy用例准确skip |
| `local\venvs\reference\Scripts\python.exe -m py_compile tools\fsr\onnx_segment_p3.py tests\fsr\test_onnx_segment_p3.py` | exit0 | 语法检查 |

- 审阅：实际GPT-6 Astra medium发现来源认证可绕过的P1，以及CLI不可运行、输出竞争覆盖、严格类型绕过和external data拒绝过晚四项P2；首轮修复后又发现默认manifest摘要未固定的P2，现以单次bytes快照先验固定SHA再解析，复审`APPROVE`，无剩余阻断。
- 未测/限制：ONNX `QuantizeLinear`为nearest-even，而CPU参考为simulator-derived half-away；本批只证明静态真实p3图可重建并通过checker，未跑ORT数值。不是完整ONNX、官方golden、QAIRT/QNN/HTP、设备或游戏验证。
- 状态与下一步：F04a `complete`；按用户指示本轮到此停止，后续叶F04b。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
