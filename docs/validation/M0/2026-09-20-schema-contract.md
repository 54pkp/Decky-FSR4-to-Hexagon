# M0 S0 schema contract validation

## 基本信息

```yaml
report_schema_version: draft-0
run_id: m0-s0-20260920-1532-cst
milestone: M0
work_package: S0-schema-contract
source_commit: fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d
dirty_tree: true
started_at: 2026-09-20T15:18:00+08:00
finished_at: 2026-09-20T15:32:01+08:00
evidence_level: host_test
gate: pass
device_profile_id: null
model_manifest_id: null
service_instance_id: null
actual_backend: none
```

## 本次目标和适用范围

- 验证行为：冻结 FIRST_BATCH S0 的设备档案 schema、CLI/退出码、fixture/runner 和输出目录协议。
- 不覆盖：采集器、离线工具、真实 Linux 行为、Odin 3、SDK、NPU、游戏或设备验证。
- 环境：Windows 开发主机，PowerShell；Python 3.12.7；`jsonschema` 4.26.0。
- 依赖核对：[官方 PyPI 发布信息](https://pypi.org/project/jsonschema/4.26.0/)显示 4.26.0 支持 Python >=3.10；本机实际导入版本为 4.26.0。

## 检查记录

| 检查 ID | 层级 | 实际命令/操作 | 退出码 | 观察结果 | gate | 证据路径与 SHA-256 |
| --- | --- | --- | ---: | --- | --- | --- |
| S0-JSON | host_test | `python -m json.tool tools/device/schema/device-profile.schema.json` | 0 | JSON 语法有效 | pass | `tools/device/schema/device-profile.schema.json` `8748f990a4e350bc928c248d2c6a7bd0aacc2c85855221ada67a23e92607d1ea` |
| S0-META | host_test | `Draft202012Validator.check_schema(schema)` | 0 | Draft 2020-12 validator 接受 schema | pass | 同上 |
| S0-POSNEG | host_test | 使用 `Draft202012Validator(..., FormatChecker())` 校验内存中的完整 fixture 文档，再将 `gate` 改为 `pass` | 0 | 合法示例通过；fixture 冒充 pass 被拒绝 | pass | 命令输出 `valid-and-negative-ok`（本报告记录） |
| S0-DEP | host_test | `python -c "from importlib.metadata import version; print(version('jsonschema'))"` | 0 | `4.26.0` | pass | `tools/device/requirements-host.txt` `756cc9e506ae4ee1a6f6c0507088b5cfc0dc8ba350fb2d2d46f1ffa72033adb6` |
| S0-DOC | source_review | 对照 FIRST_BATCH S0 八项检查 schema README | 0 | CLI、退出码、目录、脱敏边界、fixture 和 runner 已固定 | pass | `tools/device/schema/README.md` `9204f6e0389a76b0acc291a23b21339616b186732707f5c997e38eb817344f23` |

## 正确性与失败路径

- schema 拒绝未知结构字段、非法 evidence 路径、错误哈希格式、示例/fixture 的非 `not_run` gate，以及失败状态和失败类别不一致。
- 私有档案必须没有 redaction 元数据；公开档案必须有 `public-v1` 元数据且不得引用 private evidence。
- 依赖缺失时由后续工具明确失败；本批不实现或验证静默降级路径。
- `gate` 与字段 `status` 分离；本报告的 host pass 只证明 S0 合同可被主机 validator 执行。

## 结论与交接

- `host_test/pass`：A/B 可以只读 schema README 和 schema 开始实现。
- `device_test: not_run`；真实 Linux、Odin 3、CDSP/FastRPC/HTP 和游戏均未运行。
- M0 未完成；S0 只是本批共享合同冻结。
- 没有修改 `docs/architecture/CONTRACTS.md` 的共享 `draft-0` 核心语义，无需 ADR。
