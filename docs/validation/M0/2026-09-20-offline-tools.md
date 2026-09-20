# M0 离线校验与公开脱敏验证报告

## 基本信息

```yaml
report_schema_version: draft-0
run_id: m0-offline-tools-20260920-01
milestone: M0
work_package: FIRST_BATCH-B-offline-tools
source_commit: 91ae78e2042a4c8971b39a8abd381a0705ab7085
dirty_tree: true
started_at: null
finished_at: 2026-09-20T15:43:21+08:00
evidence_level: host_test
gate: pass
device_profile_id: null
model_manifest_id: null
service_instance_id: null
actual_backend: none
```

开始时间未在首条命令前采集，故如实保留 `null`；本报告没有设备时钟或设备运行记录。

## 本次目标和适用范围

- 验证 `validate` 对 Draft 2020-12 schema、格式、引用关系及落盘 evidence 哈希/字节数的离线检查；验证错误含稳定字段路径。
- 验证 `redact` 的 `public-v1` 确定性替换、公开文本 evidence 新路径/新哈希、未发布私有 evidence 引用移除及拒绝覆盖。
- 不覆盖采集器、Linux 实机、Odin 3、CDSP/FastRPC/HTP、Steam/Proton 实际安装或游戏链路。
- `device_test: not_run`；`game_test: not_run`。主机 fixture 通过不代表设备或硬件通过。

## 环境与资产

| 项目 | 实际值及来源 |
| --- | --- |
| 主机 | Windows 主机；Python 3.12.7（测试命令输出） |
| validator | `jsonschema 4.26.0`，精确版本检查；`Draft202012Validator` + `FormatChecker` |
| 设备/SDK/runtime | 未使用；无设备访问；不适用 |
| 基线 | Git `91ae78e2042a4c8971b39a8abd381a0705ab7085`；共享工作区有未提交文件 |
| golden 来源 | `tools/device/fixtures/comprehensive/`（含 `expected/public-command.txt`）由 Worker B 按冻结 schema/README 手工构造，未导入或调用 `collect.py` 的内部解析逻辑 |

关键资产 SHA-256：

- `tools/device/profile_tools.py`: `6a2058c557d8b1752cff5395005af330eb63e967381cb3a41d50ae5f5af246a3`
- `tools/device/fixtures/comprehensive/expected/device-profile.json`: `3f293428ab62f828854f66e4e9f5117dcd307321e296c33722fea716ea8835bc`
- `tests/device/test_profile_tools.py`: `c7e82ae05795d22e733df86034b21a3f24ea74aea552a6d449725b706abf9121`

## 检查记录

所有命令的工作目录均为仓库根目录。

| 检查 ID | 层级 | 实际命令 | 退出码 | 观察结果 | gate |
| --- | --- | --- | --- | --- | --- |
| B-01 | host_test | `python -m unittest discover -s tests/device -v` | 0 | 17 项通过；覆盖 CLI redact/validate 往返、成功/缺失/不可用/权限/超时/非零/空 evidence/截断/空格路径、未知字段、非法 gate/evidence level、坏路径/hash/引用、示例冒充实测、依赖缺失/版本错误、脱敏与拒绝覆盖 | pass |
| B-02 | build | `python -m py_compile tools/device/profile_tools.py tests/device/test_profile_tools.py` | 0 | Python 语法编译通过 | pass |
| B-03 | host_test | `python tools/device/profile_tools.py validate tools/device/fixtures/comprehensive/expected/device-profile.json` | 0 | 独立 golden profile 及其 evidence 字节/hash 通过 | pass |
| B-04 | source_review | `python -m json.tool tools/device/fixtures/comprehensive/expected/device-profile.json` | 0 | golden JSON 可解析 | pass |
| B-05 | source_review | `git diff --check -- tools/device/profile_tools.py tools/device/fixtures tests/device` | 0 | 无空白错误 | pass |
| B-06 | device_test | 未执行 | null | 无目标设备访问 | not_run |
| B-07 | game_test | 未执行 | null | 不在本工作包范围 | not_run |

## 正确性与失败路径

- 校验器在 schema 通过后检查 evidence ID 唯一性、观察项引用存在性、安全相对路径，以及 evidence 文件 SHA-256/字节数；schema、profile JSON 或语义不合法返回 `1`，输入/覆盖错误返回 `2`，依赖或 I/O 致命错误返回 `3`。
- `jsonschema` 缺失或不等于 `4.26.0` 时明确致命失败，不存在自制降级 validator。
- 脱敏从 identity 建立用户/主机哨兵，覆盖同类个人路径、带标签的序列式标识及 UTF-8 evidence 文本；哈希和 evidence ID 等技术关系字段不会被普通 token 替换破坏。
- 公开文本 evidence 使用新路径并按改写后字节重算 SHA-256/byte count；本策略不发布非 `.txt`/`.log`/`.json` 私有 evidence，并从所有 observation 引用移除。测试再次对公开 profile 和落盘 evidence 做完整校验。
- 同一输入两次运行除 `redacted_at` 外得到相同结构、路径、替换文本和哈希；时间字段明确记录每次脱敏发生时间。

## 结论与交接

- 本工作包的主机离线行为 gate 为 `pass`；能证明冻结 CLI 消费端在该 Windows/Python 环境的离线行为。
- 不能证明 `collect.py` 与本工具的组合集成，也不能证明任何 Linux/设备/NPU/HTP/游戏行为。
- 未修改 schema、requirements、collector、README、公共状态或共享合同；接口偏差：无。
- 集成者下一步应使用 A 的实际 fixture 输出运行 `validate` 和 `redact`，检查生产者/消费者一致性；目标设备检查继续保持 `not_run`。
