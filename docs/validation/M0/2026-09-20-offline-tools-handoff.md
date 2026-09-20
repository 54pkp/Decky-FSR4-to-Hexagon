# FIRST_BATCH Worker B：离线工具交接

## 当前现场

- 工作包：M0 `FIRST_BATCH-B-offline-tools`，2026-09-20。
- 基线：`91ae78e2042a4c8971b39a8abd381a0705ab7085`；共享工作区 dirty，未 stage/commit/切分支。
- owner/角色：Worker B；GPT-5.6 Sol / medium（由协调者分配）。
- 环境：Windows、Python 3.12.7、`jsonschema 4.26.0`；无设备访问。
- 完整证据：[2026-09-20-offline-tools.md](2026-09-20-offline-tools.md)。

## 已完成的变化

| 文件/模块 | 行为变化 |
| --- | --- |
| `tools/device/profile_tools.py` | 冻结 CLI 的离线 `validate`/`redact`；严格 Draft 2020-12 + format；引用/落盘 evidence 校验；确定性 `public-v1`；拒绝覆盖与统一退出码 |
| `tools/device/fixtures/**` | 手工独立 comprehensive/profile/evidence/command golden 与公开脱敏文本 golden；全部 profile 为 `example_only: true`、`gate: not_run` |
| `tests/device/test_profile_tools.py` | 17 项无设备 unittest，覆盖冻结卡列出的成功与失败边界及 CLI 往返 |
| `docs/validation/M0/2026-09-20-offline-tools*.md` | 实际主机证据与本交接 |

## 尚未完成或验证

- `device_test: not_run`，`game_test: not_run`；未接触 Odin 3、Linux 实机、CDSP/FastRPC/HTP。
- 尚未由 integrator 把 A 的 collector 输出送入 B 的 CLI 做组合检查。
- 未验证缺少/错误版本 `jsonschema` 的真实隔离环境；代码路径为显式致命失败，单元测试未卸载当前依赖。

## 决定与合同

- 没有修改 `draft-0` schema 或共享合同，无 ADR。
- 公开 profile 生成稳定的 `public-<private-profile-sha256-prefix>` ID，并将 `supersedes` 设为 `null`，避免私有 ID/历史 ID 泄露；原私有文件关联由 `redaction.source_profile_sha256` 保留。
- `public-v1` 仅发布可安全按 UTF-8 处理且扩展名为 `.txt/.log/.json` 的 evidence；其余私有 evidence 不附带并移除引用。

## 复现

```text
python -m unittest discover -s tests/device -v
python -m py_compile tools/device/profile_tools.py tests/device/test_profile_tools.py
python tools/device/profile_tools.py validate tools/device/fixtures/comprehensive/expected/device-profile.json
```

最后一次测试：17/17 通过，退出码 0。不要覆盖其他 agent 的 `collect.py`、`tools/device/README.md`、schema、requirements 或公共状态文件。

## 下一位应当做什么

1. Integrator 检查本 diff 与 A 的 diff 文件归属，然后用 collector 生成一个全新的临时输出目录。
2. 对生成的私有 profile 运行 `validate`，再运行 `redact --output <new-file>` 并验证公开 profile；预期均为 0，重复输出预期为 2。
3. 若生产者形状与冻结 schema 不一致，先作为明确接口偏差协调更新生产者/消费者；不要由 B 暗改共享 schema。
4. 集成报告仍将真实 Linux 和 `device_test` 写为 `not_run`。
