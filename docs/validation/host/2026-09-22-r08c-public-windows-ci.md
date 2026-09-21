# 2026-09-22 / R08c 公开Windows CI合同

- 目标与范围：基于`bb82fe6bbdea5464a13891345b4117ae11bfdfb3`增加不依赖私有SDK/资产的GitHub Actions Windows x64公开基线；不运行R08a私有多venv矩阵。
- 实现与验收：`windows-2022`精确矩阵覆盖最低Python3.10与当前锁定3.12.14；Actions锁到40位commit，只读权限且checkout不保留凭据。仅安装公开`requirements-host.txt`、执行`pip check`及verbose全基线，capability skip保持skip。离线合同测试拒绝secret、私有路径/依赖和非固定Action。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅待`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.host.test_public_ci -v` | exit0；8/8通过 | 离线workflow合同，含PowerShell原生命令失败传播 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；294 tests，246 pass / 48 skip | 本机Python3.12.14 Windows host，不是云端矩阵 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现同一PowerShell块中`pip check`可能掩盖前一条`pip install`失败；已拆成独立step并增加每块单条原生命令的合同回归。最终复审`APPROVE`，无剩余阻断。
- 未测/限制：新workflow尚未在GitHub-hosted runner触发；Python3.10 job为已固化合同而非已运行证据。ARM64/Linux、私有SDK/资产、私有多venv、HTP、设备和游戏均`not_run`。
- 状态与下一步：R08c `complete`；下一叶R09，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
