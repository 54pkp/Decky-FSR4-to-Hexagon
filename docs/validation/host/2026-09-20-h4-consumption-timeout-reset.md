# 2026-09-20 / H4 消费、超时与换代隔离

- 目标与队列项：完成 H4 主机生命周期回放；把执行完成与 `result_consumed` 分离，成功消费后才提交 synthetic candidate history，失败/超时使 history 失效；timeout 保留资源直到匹配完成，reset 隔离旧代资源并幂等推进 generation。
- 基准提交、变更范围：`943b3224e825815e82fa1fa7f2da693e47485c2b`；审阅代码 diff `c8d97bbe6edd89838bf9c09181246bc9e81b40d2`；修改 `tools/replay/lifecycle.py`、对应测试、STATUS 与本记录。
- 实际模型/强度：协调宿主未暴露当前模型参数，记为 unknown；只读实现/测试核查 GPT-5.6 Sol / medium；批次审阅 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows；仓库 `.venv` 使用 Python 3.12.14 与 `jsonschema 4.26.0`；Git 2.49.0.windows.1；`cpu_reference` synthetic replay。系统 Python 3.9.13 未改动。无设备、QNN/HTP、GPU、游戏或真实模型执行。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests/replay -p "test_*.py" -v` | 0；24/24 通过 | host_test / pass |
| `.venv\Scripts\python.exe -m unittest discover -s tests/model -p "test_*.py" -v` | 0；49/49 通过 | host_test / pass |
| `.venv\Scripts\python.exe -m py_compile tools/replay/lifecycle.py tests/replay/test_lifecycle.py` | 0 | build / pass |
| `.venv\Scripts\python.exe tools/replay/lifecycle.py verify --manifest tools/model/fixtures/synthetic-valid.json --scenario tools/replay/fixtures/identity-replay.json` | 0 | host_test / pass |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | 0；104 项中 103 通过、1 skipped（普通 Windows symlink 权限不可用） | host_test / pass，skipped 保留 |

依赖复现：系统 `py -3` 仍指向已不存在的旧 Python 3.12 路径，Python 3.9 又不满足 `jsonschema 4.26.0` 的 Python `>=3.10` 要求。使用本机 Codex 随附 Python 3.12.14 重建忽略的仓库 `.venv`，再执行 `.venv\Scripts\python.exe -m pip install -r tools/device/requirements-host.txt` 成功；未修改系统 Python 或降低依赖版本。无外部模型、SDK、设备或游戏资产。

- 审阅：Astra medium 审查上述冻结代码 diff、合同及 H2/H3 边界，独立运行 replay 24/24，并补核 executing/pending × timeout/reset 四组组合；结论通过，无 finding。后续 STATUS 和本记录为轻量文档自检。
- 未测/限制：candidate history 仅用整数输入快照验证提交/失效状态，不代表 FSR4 recurrent 内容。Linux、Odin 3、QNN/HTP、GPU、真实 FSR4、游戏、性能、画质和功耗全部 `not_run`。
- 下一步：H1–H4 主机队列已完成；设备条件可用后另开阶段处理后置验证。
