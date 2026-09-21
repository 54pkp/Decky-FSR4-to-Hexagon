# 2026-09-22 / R08c 公开Windows CI合同

- 目标与范围：基于`bb82fe6bbdea5464a13891345b4117ae11bfdfb3`增加不依赖私有SDK/资产的GitHub Actions Windows x64公开基线；不运行R08a私有多venv矩阵。
- 实现与验收：首次云端运行证明3.12.14无Windows2022 x64资产后，R08c验收同步改为`windows-2022`公开可安装的固定矩阵：最低支持3.10线的最后Windows installer（3.10.11）与3.12线的最后Windows installer（3.12.10）。本地bundled/source-built 3.12.14仍由R08a单列，在公开CI为`not_run`。Actions锁到40位commit，只读权限且checkout不保留凭据。仅安装公开`requirements-host.txt`、分步执行安装/`pip check`及verbose全基线，capability skip保持skip。
- 实际角色：协调者型号/强度无独立回执，记`unknown`；worker实际`gpt-5.6-sol / medium`；冻结diff审阅待`gpt-6-astra / medium`。

## 检查

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.host.test_public_ci -v` | exit0；9/9通过 | 离线workflow合同，含PowerShell失败传播与可安装patch锁定 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py` | exit0；295 tests，247 pass / 48 skip | 本机Python3.12.14 Windows host，不是云端矩阵 |
| [GitHub Actions run 35664182404](https://github.com/54pkp/Decky-FSR4-to-Hexagon/actions/runs/35664182404) | Python3.10 success；3.12.14在setup-python失败 | 首次push如实保留；3.12.14无Windows2022 x64资产，未运行测试 |
| [GitHub Actions run 35665191724](https://github.com/54pkp/Decky-FSR4-to-Hexagon/actions/runs/35665191724) | conclusion `success`；Python3.10.11 / 3.12.10双job success | 修复后真实GitHub-hosted Windows x64矩阵 |
| `git diff --check` | exit0 | 文本检查 |

- 审阅：Astra medium初审发现同一PowerShell块中`pip check`可能掩盖前一条`pip install`失败；已拆成独立step并增加每块单条原生命令的合同回归，当时复审`APPROVE`。首次云端失败后又改为官方manifest存在的3.10.11/3.12.10 Windows x64资产并同步计划验收；最终复审`APPROVE`，无剩余代码/合同阻断。
- 未测/限制：云端仅证明Windows x64公开基线；ARM64/Linux、私有SDK/资产、私有多venv、本地3.12.14、HTP、设备和游戏在该公开CI中均`not_run`。本地3.12.14的已有证据仍由R08a单列。
- 状态与下一步：R08c `complete`；下一叶R09，远端确认本提交后才开始。
- Git交付：协调者核对origin/main和`54pkp <67623881+54pkp@users.noreply.github.com>`；实际结果以Git历史为准。
