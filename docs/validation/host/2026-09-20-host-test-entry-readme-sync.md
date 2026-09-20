# 2026-09-20 / 统一 Windows 测试入口与 README 同步

- 目标与队列项：修复根目录 unittest 发现 0 项的问题，并使中英文 README 如实列出 H2–H4 host-only 工具；同时更正 H4 记录中的审阅状态和 `py_compile` 证据分类。
- 基准提交、变更范围：`91e7c5cda5b370345a17a26bbdc64f5248e5eff0`；新增 tests package marker，更新两个 README、H4 历史记录和 STATUS；不改变运行时代码、schema 或设备 ABI。
- 实际模型/强度：协调与实现 unknown / unknown；批次审阅待冻结 diff 后由 GPT-6 Astra / medium 执行。
- 环境、工具版本、实际后端：Windows；Python 3.12.7；Git 2.54.0.windows.1；离线 host tests，无设备后端。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `py -3 -m unittest discover -s tests -p "test_*.py" -v` | 0；95 项中 93 通过、2 skipped（Windows symlink 权限不可用） | host_test / pass，skipped 保留 |
| `py -3 -m py_compile tests/__init__.py tests/device/__init__.py tests/model/__init__.py tests/replay/__init__.py` | 0 | build / pass |
| 中英文 README 内容与命令对照 | 均列出 device/model/replay host-only 能力及同一统一命令；均声明无运行时、HTP/设备/游戏证据 | source_review / pass |

- 审阅：GPT-6 Astra / medium 审阅 base `91e7c5cda5b370345a17a26bbdc64f5248e5eff0` 到 tree `8f996330da32d646c92028e7517290928bf046ee` 的全部 9 文件，核对 95 项 discovery、README 双语边界与 H4 历史证据修正；结论 pass，无 P0–P3 finding。
- 未测/限制：两项 symlink 测试仍因 Windows 权限 skipped；Linux、Odin 3、QNN/HTP、真实 FSR4、设备与游戏均 `not_run`。仓库仍无 CI；许可证仍需项目所有者选择，未在本批擅自添加。
- 下一步：继续 H4，补齐 timeout/pending consumption、显式消费后的 history 提交与 reset/new generation 隔离。
