# 2026-09-20 / Windows CPU 工作流精简

- 目标：将当前开发收敛到 Windows 理论、离线与 CPU 验证；提供单批停止与 Goal 续跑入口。
- 基准：`97650fd384c1443668829bcf3cfc9a3dc5f041f4`；范围为根 README/AGENTS、Codex 角色指令、STATUS、AI 指南、模板提示和路线索引。未改运行时代码。
- 分工：三位 GPT-5.6 Sol / medium，分别整理双语首页、启动提示、只读范围核查；协调者本轮模型为用户选择的 GPT-6，精确强度不可见，未声称配置使当前会话变成 Sol。
- 环境：Windows 11 build 26200、Python 3.12.7 AMD64、jsonschema 4.26.0；后端为现有主机工具，无 NPU。

## 检查

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| `python -m unittest discover -s tests/device -v` | 退出 0；28 项中 26 通过、2 skipped | worker 实际运行；Windows 普通文件 symlink 权限缺失，未当作通过 |
| TOML、Markdown 本地链接、文本编码检查 | 退出 0；42 份 Markdown、150 个本地链接，无编码/链接错误，角色 TOML 均可解析 | Python 标准库一次性检查，包含新提示与批次模板 |
| `git diff --check` | 退出 0 | 完整跟踪差异；新增文档也经文本检查 |

取消日常强制工作卡、独立审阅包/交接、每 worker 一套报告、重复全仓审阅与成本统计。改为一份短批次记录加 STATUS，重要代码/合同保留真实 diff 审阅。详细路线、旧模板、历史来源及验证报告按需参考；不删除技术证据。

- 审阅：GPT-6 Astra / medium 对上述基准的 16 份跟踪文件差异与 3 份新增文件逐项只读核查，`review_verdict=pass`。核对了双语首页、H1–H4 边界、单次停止/Goal 终点及角色配置，无必须修复项；本行仅补录已返回的结论。
- 未测：本次没有执行新的 H1 完整 fixture 链路，H1–H4 保持 not_started。Linux 特有行为、Odin 3、HTP 和游戏均 not_run。
- 下一步：从 STATUS 的 H1 开始一个小批次；本次仅重构工作流，不自行启动长期 Goal。
