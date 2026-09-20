# 2026-09-20 / P1 Windows 环境入口

- 目标与基准：基于 `895b9f382621b39ba11c695c1bc1c25deaa4c470` 实现显式 Python 路径的只读预检和一次性 venv 初始化，不覆盖既有路径，也不依赖 `py` launcher 或固定 Codex 路径。
- 产物：`tools/host/environment.py` 的 `check` / `init`、简短说明和 15 项 host 测试；中英 README 改用统一入口。入口要求 Python 3.10+、64 位 AMD64/ARM64 和 pip，原子预留目标，使用 pip isolated 模式安装基线 requirements，再执行 `pip check` 并回读精确锁定的 distribution 版本。
- 环境：Windows AMD64。现有仓库 `.venv` 为 Python 3.12.14；本次动态读取其 `sys._base_executable`，实际来源为 `C:\Users\22388\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。通用命令仍要求调用方提供 `<Python-3.10+-完整路径>`，不固化该本机路径。系统 Python 3.9.13 未修改。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.host.test_environment -v` | 退出 0；15/15 通过，含 3.9、32 位/未知架构、缺 pip、无效路径、既有目录/文件/断链、创建竞争、带空格 argv、`pip check` 失败及缺失锁定 distribution |
| 系统 Python 3.9.13 执行 `environment.py check --python <同一3.9路径>` | 退出 2；明确报告需要 Python 3.10+，无 traceback |
| 设置虚假 `PIP_TARGET` 和会导致解析失败的 `PIP_CONFIG_FILE` 后执行 `environment.py init --python <动态3.12基础解释器> --venv <带空格临时路径>` | 退出 0；报告 Python 3.12.14 AMD64，忽略重定向/配置文件，安装并回读 `jsonschema==4.26.0`，`pip check` 通过 |
| 新环境执行 `-m unittest discover -s tests -p "test_*.py"` | 退出 0；119 项中 118 通过、1 skipped（普通 Windows symlink 权限不可用） |
| `git diff --check` | 退出 0；仅显示 README 下次写入将 LF 转 CRLF 的工作树提示 |

- 失败语义：目标只要已经存在就拒绝，断链也不跟随；创建或安装开始后的失败保留部分环境供检查，用户确认后手工删除再重试。真实临时验收环境及先前 worker smoke 环境均在核对绝对路径后删除。
- 审阅：Astra medium 对初始 tree `ffe65bfca12e0fd9b88fd2a39d14330a85197a5d` 提出目标创建竞争和 pip 目标配置可越过 venv 两项问题；第一次修复复核又发现 `PIP_CONFIG_FILE` 例外。已用原子目录预留、禁用 pip 配置文件与目标变量、isolated/require-virtualenv、锁定 distribution 回读及回归/实际污染环境测试修复；对 tree `0f27c746e2932865bd9059d5e881a2bed3a8cfcd` 最终聚焦复核通过，无剩余问题。其后仅补本条审阅结论。
- 未测：未安装 QAIRT/QNN、未使用 FSR 权重、未连接 Odin 3；Linux、ARM64 实机解释器、HTP、GPU、设备和游戏均 `not_run`。ARM64/异常架构为合成 probe 单元测试，不是 ARM64 执行证明。
- 下一批：P2 外部资产登记与只读核验；本轮到此停止。
