# FIRST_BATCH M0 host tools review packet

## 1. 审阅身份

- 审阅包 ID：`m0-first-batch-review-01`
- 工作包：S0 + A + B + I，M0 主机侧只读设备建档工具
- 作者/Owner：Sol integrator、Worker A、Worker B
- 审阅者：`fsr4_reviewer`（项目角色锁定 GPT-6 Astra / high）
- Integrator：主协调器
- 审阅时间：待 reviewer 填写

## 2. 精确 diff 身份

### 已提交分支

- 仓库：`C:\Users\pankaiping\Documents\ChatGPT\Decky FSR4 to Hexagon`
- Base：`fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d`
- Head：`6e4e6c87c51b33b1ef85b8bcd63e4904125d07af`
- 审阅命令：`git diff --find-renames fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d..6e4e6c87c51b33b1ef85b8bcd63e4904125d07af -- tools/device tests/device docs/validation/M0`
- 工作树在冻结 Head 后仅新增本审阅包；它是索引，不属于被审代码。

## 3. 必须直接读取的内容

### 所有变更

| 路径 | 变更目的 | 重点 |
| --- | --- | --- |
| `tools/device/schema/device-profile.schema.json` | Draft 2020-12 M0 schema | 观察失败、example/gate、private/public、evidence 路径 |
| `tools/device/schema/README.md` | 冻结 CLI、输出、fixture/runner 协议 | 生产者/消费者是否一致、未附带 evidence 语义 |
| `tools/device/requirements-host.txt` | 锁定 validator | 4.26.0 与运行时检查 |
| `tools/device/collect.py` | Linux 只读 collector | 只读边界、fixture 隔离、超时回收、大小限制、证据/manifest、ELF/PE |
| `tools/device/profile_tools.py` | validate/redact | schema/语义校验、路径 containment、脱敏遗漏、hash 重算、覆盖拒绝 |
| `tools/device/fixtures/comprehensive/**` | 独立 golden/命令/失败输入 | 是否独立于 collector、是否覆盖工作卡且无个人数据 |
| `tests/device/test_profile_tools.py` | 18 项离线测试 | 是否真正触发失败边界；symlink skip 的残余风险 |
| `tools/device/README.md` | 用户边界与运行说明 | 是否误报设备/HTP |
| `docs/validation/M0/2026-09-20-*.md` | S0、A、B、I 证据与交接 | 命令、退出码、哈希、not_run 边界是否准确 |

### 测试与证据

| 证据路径 | 命令/环境 | 退出码 | 证明范围 |
| --- | --- | ---: | --- |
| `2026-09-20-schema-contract.md` | Draft202012 check / Windows Python | 0 | S0 schema 可执行与 fixture gate 负例 |
| `2026-09-20-collector.md` | fixture、timeout、truncate、overwrite、unsafe | 0/2（按预期） | A 主机行为，不是 Linux/设备 |
| `2026-09-20-offline-tools.md` | 17 项 Worker B 测试 | 0 | 独立 golden 与脱敏消费端 |
| `2026-09-20-host-integration.md` | 18 项最终测试 + A→B CLI 往返 | 0；1 skip | 最终组合，symlink 触发仍未在本主机运行 |

最终集成命令：

```text
python -m py_compile tools/device/collect.py tools/device/profile_tools.py tests/device/test_profile_tools.py
python -m unittest discover -s tests/device -v
python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output <new path with spaces>
python tools/device/profile_tools.py validate <output>/device-profile.json
python tools/device/profile_tools.py redact <output>/device-profile.json --output <output>/public-profile.json
python tools/device/profile_tools.py validate <output>/public-profile.json
```

## 4. 关键不变量

- profile 的 `schema_version: draft-0` 与 JSON Schema Draft 2020-12 是两种版本；不得改变共享帧/生命周期合同。
- fixture/example 必须 `example_only: true`、`gate: not_run`；host pass 不能成为 `device_test/pass`。
- collector 只写显式新目录，不安装、提权、远程登录、改配置、打开设备节点或 DSP 会话；fixture 绝不执行程序。
- 命令用 argv、`shell=False`、有超时和有界 stdout/stderr；超时后 terminate/kill 并 wait。
- evidence 是安全输出相对路径，内容 hash/bytes 可复核；validate/redact 不能经 `..`、绝对路径或 symlink 读取 profile 目录外内容。
- 公开档案必须清除用户名、主机名、个人路径、序列标识和同类 evidence 内容；改写 evidence 使用新 hash，未发布私有 evidence 不得继续引用。
- Linux glibc ARM64 与 Android ARM64 不互换；本批没有 QNN/HTP/游戏结论。

## 5. 审阅问题

1. collector 的 live/fixture 成功与失败路径是否都产生 schema 可接受且不误导的状态？
2. fixture runner 是否存在程序执行、路径逃逸、宿主回退或无界读取？
3. validate/redact 是否可能跟随 evidence 逃逸、遗漏敏感片段、保留错误 hash/引用或留下半公开产物？
4. schema、producer、consumer、golden 和文档是否一致；未知字段策略是否稳定？
5. 测试是否独立且真正覆盖 timeout、空输出、非零、截断、空格路径、覆盖拒绝、依赖失败和脱敏哨兵？
6. 报告是否严格区分 source/build/host/device/game 证据？

## 6. 未测试与待决策

- 真实 Linux 行为：`not_run`；影响：不能证明 SIGALRM/sysfs symlink/字符设备权限和生产 subprocess 在 Linux 的行为。
- evidence symlink 触发：Windows 因 WinError 1314 skip；已有 containment 源码与测试，需 Linux 补跑。
- Odin 3 device gate：`not_run`；没有设备档案、CDSP/FastRPC/HTP 结论。
- 游戏 gate：`not_run`。
- 无需 reviewer 决定设备、SDK、专有资产或刷机方向；本次只裁决主机批次代码。

## 7. 成本观测

- 可观测 token/usage：unknown。
- 子任务：2 个 worker，均一次交付；integrator 一次路径 containment 修复；尚无 reviewer 返工。

## 8. 可定位发现

由 reviewer 填写；必须含文件/行或符号、触发、影响和最小修复方向。

## 9. 裁决

- `review_verdict=<pass | change | blocked>`
- 设备检查：`gate=not_run`
- 要求复审的精确范围：待 reviewer 填写。

