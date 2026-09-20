# 2026-09-20 / H2 合成 manifest 元数据校验

- 目标与队列项：完成 H2；新增仅用于 Windows/CPU 主机检查的合成 manifest/tensor 校验器与 fixture，确定性检查必需字段、shape、dtype、layout、字节数、数量和容量上限及非法 JSON。
- 基准提交、变更范围：`21b6e0e6ca402307e1f2afc9bbc6babe4535c9ec`；新增 `tools/model/manifest.py`、合成 fixture 和 `tests/model/test_manifest.py`，并更新 STATUS。没有改 M2 生产 manifest 合同或设备 ABI。
- 实际模型/强度：协调者模型/强度宿主未暴露，记为 unknown；实现与只读合同核查 worker 为 GPT-5.6 Sol / medium；批次 reviewer 为 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows 11 `10.0.26200`，Python `3.12.7`，`jsonschema==4.26.0`；校验器本身只用 Python 标准库，实际后端为离线 host CPU/合成 JSON，无模型执行。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `python -m unittest discover -s tests/model -v` | 0；20/20 passed | host_test / pass |
| `python tools/model/manifest.py verify --manifest tools/model/fixtures/synthetic-valid.json` | 0；合法合成 fixture 通过 | host_test / pass |
| `python -m unittest discover -s tests/device -v` | 0；28 项中 26 passed、2 skipped | host_test / pass；skipped 不折算为 pass |
| `python -m unittest discover -s tests -v` | 5；0 tests，现有 `tests/device` 与 `tests/model` 均非 unittest package，根目录 discovery 不递归 | host_test / fail；改用仓库既有的分目录入口，不为本批改造测试框架 |
| `git diff --check` | 0 | source_review / pass |

实现使用闭合的 `host-synthetic-manifest-v1`：仅接受 `synthetic-` manifest ID，并强制 `example_only=true`、`production_ready=false`、`validation_gate=not_run`。tensor 限定 rank 4、NHWC/NCHW、int8/uint8/float16/float32，`byte_count` 必须等于 shape 与 dtype 计算值；64 个 tensor、单 tensor 1 GiB、合计 2 GiB、单维 65536、manifest 文件 1 MiB 为显式上限。有界乘法在任何 tensor 数据读取或分配前完成。重复 tensor 名、未知字段、重复 JSON key、非有限 JSON 数（含指数溢出）、超长整数、过深嵌套以及错误类型/维度/容量均稳定拒绝且不泄漏 traceback；fixture 不含真实资产、SDK、模型哈希或设备声明。

- skipped：既有 device 回归中，Windows 普通文件 symlink 用例按平台固定跳过；evidence symlink 用例因当前账户缺少创建符号链接权限（WinError 1314）跳过。
- 审阅：GPT-6 Astra / medium 审阅完整 staged diff、合同边界和测试证据；发现极大整数、过深 JSON 与指数溢出会绕过稳定 input error（P2）。补充有界整数/有限浮点解析、窄范围异常转换及 CLI 回归后，对 tree `6e75ab30ae270bf647fbe4540c82e8d8f5b346b9` 聚焦复核通过，无剩余阻断问题。
- 未测/限制：未读取或执行任何模型；Odin 3、Linux、GPU、QNN/HTP、真实 FSR4、游戏、数值等价、画质、性能、延迟和功耗均 `not_run`。本批通过只证明合成 host manifest 元数据校验行为。
- 下一步：H3 CPU 数值参考，先实现小尺寸量化/反量化的独立固定预期、舍入/饱和/误差与声明容差；本批不启动。
