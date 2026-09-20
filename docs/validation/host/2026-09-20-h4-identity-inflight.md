# 2026-09-20 / H4 身份与单在途回放

- 目标与队列项：H4 第一小批；用 H2 manifest 与 H3 backward reprojection 建立 Windows CPU 生命周期 harness，绑定 `(service_instance_id, session_id, context_id, frame_id, history_generation, model_manifest_id)`，同 context 仅允许一个 active request，错配/过期 completion 不得清除 active。
- 基准提交、变更范围：`981a178f8b77ce96bac32bee2dad401027765f23`；新增 replay 实现、闭合 fixture、测试，补充 fixture LF 规则，并把 STATUS 的 H4 标为 `in_progress`。
- 实际模型/强度：协调 unknown / unknown；实现与只读审计 GPT-5.6 Sol / medium；批次审阅 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows；Python 3.12.7；Git 2.54.0.windows.1；`cpu_reference`，仅 synthetic host replay。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `py -3 -m unittest discover -s tests/replay -p "test_*.py" -v` | 0；15/15 通过 | host_test / pass |
| `py -3 -m unittest discover -s tests/model -p "test_*.py" -v` | 0；49/49 通过 | host_test / pass |
| `py -3 -m unittest discover -s tests/device -p "test_*.py" -v` | 0；26 通过、2 skipped（Windows symlink 权限不可用） | host_test / pass，skipped 保留 |
| `py -3 -m py_compile tools/replay/lifecycle.py tests/replay/test_lifecycle.py` | 0 | build / pass |
| `py -3 tools/replay/lifecycle.py verify --manifest tools/model/fixtures/synthetic-valid.json --scenario tools/replay/fixtures/identity-replay.json` | 0 | host_test / pass |

fixture `tools/replay/fixtures/identity-replay.json` SHA-256：`667feaa28ceb62769bcb681d4341a31b8c99828667f3661108b19d35240c1cd9`；仓库自有 synthetic 数据，无外部模型/SDK/游戏资产。

- 审阅：Astra medium 在初始 tree `a13ad745b45bbbedbe8d0f19048e5e97ef65bbc8` 发现 1 项 P2：解析器可接受的深层 payload 会在快照复制时泄漏 `RecursionError`。已归一化为 `LifecycleInvalid` 并补 parser→submit/CLI 回归；修复后定向 1/1、replay 15/15 与 `py_compile` 均退出 0，Astra 对 tree `c978ff297ccf379dfc618e369159906d58fcfb64` 聚焦复核通过，无剩余 finding。
- 未测/限制：timeout、`result_consumed`、history commit/invalidate、reset/new generation、断连与资源回收未实现；Linux、Odin 3、QNN/HTP、游戏和真实 FSR4 均 `not_run`。本结果不证明完整 FSR4 或设备行为。
- 下一步：继续 H4，补齐 timeout/pending consumption、显式消费确认后的 history 提交与 reset/new generation 隔离。
