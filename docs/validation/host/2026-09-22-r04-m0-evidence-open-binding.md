# 2026-09-22 / R04 M0 evidence打开对象绑定

- 目标与范围：基于`17e3d29840a22a28aa5c761fcd3836e3a18f71ae`关闭evidence路径检查与随后打开之间的替换窗口；验证和脱敏消费都从同一已打开句柄读取。本批不处理公开输出事务（R05），不证明POSIX或设备行为。
- 实现与验收：冻结初始profile目录身份；打开evidence后先用`fstat`确认普通文件，再以Windows `GetFinalPathNameByHandleW`取得实际对象路径并回溯根目录身份，只有匹配后才从同一stream读取。Linux使用`/proc/self/fd`读取已打开句柄路径；其它平台不具备安全原语时直接拒绝，禁止退回再次按路径解析。确定性注入令预检候选在打开时转向根外文件，validator在读取前拒绝；redactor在验证完成后的再次消费也重新绑定并拒绝，未生成公开profile。
- 实际角色：协调者会话型号/强度无独立回执，记`unknown`；worker实际为`gpt-5.6-sol / medium`；冻结diff审阅实际为`gpt-6-astra / medium`。
- 环境：Windows；基线`.venv` Python 3.12.14、jsonschema 4.26.0。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.device.test_profile_tools -v` | exit0；27/27通过 | Windows host_test；含validator/redactor路径替换注入及根内junction兼容 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；240项，202通过、38跳过 | 全仓基线；skipped不算pass |
| `git diff --check` | exit0 | 文本检查 |

- 失败与修复：首次专测因`verify_files=False`仍对尚未创建的公开输出父目录取stat，产生7 errors/1 failure；将目录身份获取限制到实际文件验证路径后通过。审阅修复新增根内junction回归时首跑因测试漏引入`os`产生1 error，补引入后复测；这些失败均保留原因且不计入最终pass。
- 审阅：`gpt-6-astra / medium`初审要求不支持平台明确拒绝，并按实际路径祖先而非relative深度核对根身份；修复并补Windows根内junction回归后独立复跑27/27，最终`pass`，无待修问题。
- 未测/限制：未运行Linux/POSIX对抗、Odin 3、HTP、FSR或游戏。公开输出仍可能在写入中途留下半成品，明确留给R05；profile JSON自身的打开策略不在R04 evidence验收。
- 状态与下一步：R04 `complete`；下一叶R05，远端确认本提交后才开始。
- Git交付：协调者已核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际提交/正常推送结果以Git历史和任务最终汇报为准。
