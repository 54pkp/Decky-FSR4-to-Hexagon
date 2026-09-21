# 2026-09-22 / R10a P7环境收据与stdout gate

- 目标与范围：基于`c1042a59afeefc71d039afc90b12c16438e03bd7`将P7 accepted receipt升级为v2，绑定实际Python/NumPy、完整规范化extractor argv和固定extractor stdout成功门；不证明来源真实性或FSR运行等价。
- 实现与验收：提取前后分别由所选解释器报告CPython版本/平台/位数与NumPy distribution/module版本，并绑定解释器文件摘要；缺项、畸形或前后漂移均拒绝发布。收据保留完整三个argv位置，将短命临时extractor路径表示为与已验证提取器哈希绑定的placeholder。固定公开提取器必须输出精确独立行`ALL GATES PASSED`，伪装前/后缀不接受。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅待`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest tests.fsr.test_intake -v` | exit0；20/20通过 | 环境/漂移/argv/stdout gate及R09回归 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；306 tests，251 pass / 55 skip | 新NumPy收据用例因能力准确skip |
| `local\venvs\fsr-extract\Scripts\python.exe tools\fsr\intake.py --sdk-root research\FSR-4.0.2-reference --extractor research\fsr4-hexagon\model\extract\build_weights.py --python local\venvs\fsr-extract\Scripts\python.exe --output artifacts\p7-fsr-v07-r10a-20260922` | exit0；v2 receipt SHA-256 `b791639c857af05a90ee6fefd492f310f472338265cdab4ae077203d4139d38b` | CPython3.12.14/win-amd64/64-bit、NumPy2.2.6；100 arrays与11/58/13 graph门通过 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium独立复跑intake 20/20并核对真实v2 receipt摘要；确认解释器同一文件/哈希、NumPy版本、前后漂移拒绝、argv绑定和精确stdout行门，最终`APPROVE`，无剩余阻断。
- 未测/限制：重跑复用已有忽略的固定v07材料，未重新从网络取得或证明上游身份；stdout哈希是运行证据，不是安全签名。不是完整FSR4、QNN/HTP、设备或游戏验证。
- 状态与下一步：R10a `complete`；下一叶R10b，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
