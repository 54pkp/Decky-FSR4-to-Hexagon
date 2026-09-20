# 2026-09-20 / M0 public-v1 脱敏边界加固

- 目标与队列项：修复审计发现的 M0 public-v1 脱敏缺陷；协议常量只在 schema 路径豁免，敏感 ID 的拼写与 JSON 类型全部覆盖，任意 observation `value` 不参与真实 evidence 关系校验/重映射，公开 candidate ID 使用新生成值。
- 基准提交、变更范围：`7948693f44ef8514bee7d8ff7a053d7f3fe65241`；修改 `profile_tools.py` 与对应测试，更新 STATUS；不改变 schema、H2–H4 实现或设备 ABI。
- 实际模型/强度：协调 unknown / unknown；实现与只读合同核查 GPT-5.6 Sol / medium；批次审阅待冻结 diff 后由 GPT-6 Astra / medium 执行。
- 环境、工具版本、实际后端：Windows；Python 3.12.7；Git 2.54.0.windows.1；`jsonschema==4.26.0`；离线 host redaction，无设备后端。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| 聚焦 protocol path、伪 observation、敏感类型与悬空引用 4 项 unittest | 0；4/4 通过 | host_test / pass |
| `py -3 -m unittest discover -s tests/device -p "test_*.py" -v` | 0；31 项中 29 通过、2 skipped（Windows symlink 权限不可用） | host_test / pass，skipped 保留 |
| `py -3 -m unittest discover -s tests/model -p "test_*.py" -v` | 0；49/49 通过 | host_test / pass |
| `py -3 -m unittest discover -s tests/replay -p "test_*.py" -v` | 0；15/15 通过 | host_test / pass |
| `py -3 -m py_compile tools/device/profile_tools.py tests/device/test_profile_tools.py` | 0 | build / pass |

- 审阅：GPT-6 Astra / medium 审阅 base `7948693f44ef8514bee7d8ff7a053d7f3fe65241` 到 tree `ebae1447e9d8c4eebe7947f46ce95a1c00a59f4a` 的完整四文件差异，并只读复跑 4 项聚焦测试与额外 JSON evidence 检查；结论 pass，无 P0–P3 finding。
- 未测/限制：Windows 普通文件 symlink 与 evidence symlink 两项仍因权限 skipped；Linux 实时采集、Odin 3、QNN/HTP、真实 FSR4、设备与游戏均 `not_run`。公开输出仍只按 public-v1 已声明规则处理，不能替代发布前的数据治理检查。
- 下一步：单独修正中英文 README 的主机工具清单并提供统一 Windows 测试入口，再继续 H4 生命周期批次。
