# M0 FIRST_BATCH host integration validation

## 基本信息

```yaml
report_schema_version: draft-0
run_id: m0-host-integration-20260920-1548-cst
milestone: M0
work_package: FIRST_BATCH-I-host-integration
source_commit: 91ae78e2042a4c8971b39a8abd381a0705ab7085
dirty_tree: true
started_at: 2026-09-20T15:44:00+08:00
finished_at: 2026-09-20T15:48:43+08:00
evidence_level: host_test
gate: pass
device_profile_id: device-fixture-generated-randomly
model_manifest_id: null
service_instance_id: null
actual_backend: none
```

## 本次目标和适用范围

- 组合验证 Worker A 的 collector 输出可由 Worker B 的 validate/redact 消费，并核对失败路径、证据哈希和公开产物。
- 环境：Windows 开发主机、PowerShell、Python 3.12.7、jsonschema 4.26.0；没有 Odin 3 或 Linux 设备访问。
- 不覆盖：真实 Linux `/proc`/`sysfs`/设备节点、设备身份、CDSP/FastRPC/HTP、SDK、Steam/Proton 或游戏。

## 检查记录

| 检查 ID | 层级 | 实际命令/操作 | 退出码 | 观察结果 | gate | 证据 |
| --- | --- | --- | ---: | --- | --- | --- |
| I-SYNTAX | build | `python -m py_compile tools/device/collect.py tools/device/profile_tools.py tests/device/test_profile_tools.py` | 0 | 三个 Python 文件可编译 | pass | 源码哈希见下 |
| I-SUITE | host_test | `python -m unittest discover -s tests/device -v` | 0 | 18 项：17 pass，1 项 Windows 无符号链接权限而 skip | pass | 控制台输出；skip 单列为 I-SYMLINK |
| I-COLLECT | host_test | `collect.py --fixture-root .../comprehensive --output <new path with spaces>` | 0 | 生成 private profile、evidence 和 manifest | pass | profile `c7b9dffcf4dfe9b863aa44732b304c260da0f072285dc98c34e7126be1157f7e`；manifest `44f808ed1d902b6f19fca8dc25167ccc85a8112b9cdafc9aab772abf8f170ccb` |
| I-VALIDATE-PRIVATE | host_test | `profile_tools.py validate <collector>/device-profile.json` | 0 | A 输出通过 schema、关系和物理 evidence 校验 | pass | I-COLLECT |
| I-REDACT | host_test | `profile_tools.py redact <private> --output <collector>/public-profile.json` | 0 | 产生 public-v1 档案 | pass | public profile `db9b029b9aab42958e10cd6eb899874a4607bb4d8470b95f32e2e2fe54bd2a5c` |
| I-VALIDATE-PUBLIC | host_test | `profile_tools.py validate <collector>/public-profile.json` | 0 | 公开档案及公开 evidence 可复核 | pass | I-REDACT |
| I-OVERWRITE | host_test | 重复 collector 和 redact 到既有目标 | 2 / 2 | 两个入口均拒绝覆盖 | pass | stderr 诊断已观察 |
| I-MANIFEST | host_test | 对 manifest 的 6 个 artifact 重算 SHA-256/byte count | 0 | 全部匹配 | pass | 输出 `manifest-artifacts-ok 6` |
| I-UNSAFE | host_test | fixture 下传 `--steam-path ../escape` | 2 | 在创建输出目录前拒绝；目标不存在 | pass | 输出 `unsafe_created=False` |
| I-TIMEOUT | host_test | `ProductionRunner.run([python, -c, sleep(30)], 0.1)` | 0 | `timed_out=true`，进程已 terminate/kill 后 wait；exit code 1 | pass | 输出 `timeout-reaped 1` |
| I-SYMLINK | host_test | evidence symlink 逃逸单元测试 | null | Windows 返回 WinError 1314，测试 skip；实现增加 resolved-path containment，待 Linux 补跑 | not_run | `test_evidence_symlink_cannot_escape_profile_directory` |
| I-SETUP-FAILURE | host_test | 首次将输出放在不存在的父目录下 | 3 | 明确 I/O fatal；修正为先创建父目录后通过 | pass | 保留为已观察失败，不代表 collector 缺陷 |
| I-DEVICE | device_test | 未执行 | null | 无 Odin 3 连接 | not_run | 无 |
| I-GAME | game_test | 未执行 | null | 不在本批范围 | not_run | 无 |

最终源码 SHA-256：

- `tools/device/collect.py`: `aea1576300eb3d5da0b42d54410571c132b8966747ea45250c5a18484da7a6fa`
- `tools/device/profile_tools.py`: `8ad75279bfa93fe727dd078e193fcd2d73ff056d741d88aab4f26023f67a943c`
- `tests/device/test_profile_tools.py`: `403f87a55d10a98f64d479b93f289eff8e64453fa36167cc71d059d963e3c213`

临时组合产物位于 `%TEMP%/decky-m0-integration-c3734d26eaa84f4c8373b63734a27df7/`，仅作本机证据，不提交仓库，也不是设备档案。

## 集成修复与正确性边界

- 集成审查发现仅靠词法相对路径不足以阻止 evidence 符号链接逃逸；`profile_tools.py` 现在解析真实路径并要求其仍位于 profile 目录内，避免 validate/redact 跟随外部 evidence。
- Windows 主机无创建符号链接权限，因此该触发测试保留 `not_run`；正常路径、`..`/绝对路径和坏哈希均已执行。
- fixture 命令精确匹配 argv 且不执行 fixture 程序；生产 runner 使用 `shell=False`、双线程排空 stdout/stderr，并在超时后回收子进程。
- 本报告的 `host_test/pass` 只证明此 Windows/Python/fixture 组合下的工具行为。timeout 不涉及 GPU/NPU，也不说明设备工作已停止。

## 结论与交接

- FIRST_BATCH 主机集成 gate 为 `pass`，可冻结实际 diff 交给 Astra 审阅。
- 真实 Linux 行为为 `not_run`；Odin 3 `device_test: not_run`；`game_test: not_run`。
- M0 节点仍为 `in_progress`，不能标记 complete；没有 HTP、QNN 或游戏可用性结论。

