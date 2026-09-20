# M0 FIRST_BATCH Astra review fixes

## 基本信息

```yaml
report_schema_version: draft-0
run_id: m0-review-fixes-20260920-1559-cst
milestone: M0
work_package: FIRST_BATCH-review-fixes-01
source_commit: 6e4e6c87c51b33b1ef85b8bcd63e4904125d07af
dirty_tree: true
started_at: 2026-09-20T15:52:00+08:00
finished_at: 2026-09-20T15:59:02+08:00
evidence_level: host_test
gate: pass
device_profile_id: null
actual_backend: none
```

## 审阅输入与修复范围

初审角色为项目 `fsr4_reviewer`（GPT-6 Astra / high），对冻结
`fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d..6e4e6c87c51b33b1ef85b8bcd63e4904125d07af`
给出 `review_verdict=change`，`device gate=not_run`。本次只修改 reviewer 指定范围：

1. fixture `root/`、`commands.json` 与引用的 resolved containment；
2. 生产 runner 的进程组/树回收和有界 pipe drain；
3. public-v1 的空格个人路径、结构化 serial、公开 evidence ID/文件名；
4. 协议常量不受普通用户名 token 替换；
5. 公开 evidence 写入目标的 resolved containment。

## 检查记录

| 检查 ID | 实际命令/操作 | 退出码 | 观察结果 | gate |
| --- | --- | ---: | --- | --- |
| F-SYNTAX | `python -m py_compile tools/device/collect.py tools/device/profile_tools.py tests/device/test_collect.py tests/device/test_profile_tools.py` | 0 | 修复范围可编译 | pass |
| F-SUITE | `python -m unittest discover -s tests/device -v` | 0 | 26 项：24 pass、2 skip | pass |
| F-PROCESS-TREE | 子进程生成继承 pipe 的 30 秒后代，runner timeout 0.1 秒 | 0 | runner 在 4 秒门槛内返回 `timed_out` | pass |
| F-LEADER-EXIT | leader 正常退出，30 秒后代继承 pipe | 0 | Windows Job Object 关闭后后代 PID 不存活，reader 线程清零 | pass |
| F-FIXTURE-ROOT | 普通 case 的 `root/` junction 指向 case 外 | 0 | 回归测试要求 `InputError`，本机通过 | pass |
| F-COMMANDS-LINK | `commands.json` 指向 case 外 | null | Windows 普通文件 symlink 权限不可用，skip；源码 containment 已实现 | not_run |
| F-REDACTION | `user_name=user/dev`、含空格 home path、结构化 serial、敏感 private basename/ID | 0 | `source.kind`/固定工具名仍合法；所有哨兵从公开 profile/evidence/路径消失 | pass |
| F-JSON-EVIDENCE | `.json` evidence 内结构化 `serial_number` | 0 | 解析后按字段语义脱敏、重新序列化并重算 hash | pass |
| F-FIXTURE-INPUT | 缺失 `commands.json` 或 `root/` | 2 / 2 | CLI 归类为输入错误，不回归成 fatal 3 | pass |
| F-PUBLIC-DEST | `public/evidence` junction 指向 sibling | 0 | redact 拒绝，外部目录保持空 | pass |
| F-ROUNDTRIP | collector fixture → private validate → redact → public validate | 0/0/0/0 | 组合通过；公开 evidence 5 项且均为 public | pass |
| F-EVIDENCE-SYMLINK | 私有 evidence 文件 symlink 逃逸 | null | Windows WinError 1314，原有测试 skip；resolved containment 保留 | not_run |
| F-DEVICE | Odin 3 device_test | null | 未连接设备 | not_run |

最终组合临时目录：`%TEMP%/decky-m0-review-final-075631bba92b44fd8e75cca0f6a91a02/`。

最终修复工作区源码 SHA-256（提交后以复审 diff 身份为准）：

- `collect.py`: `8febc5a973988dfc1a2af47c70d3ff937c9e43f7cfb061330f6bf917cb3da79d`
- `profile_tools.py`: `ec9d67d86bed0dc6a49293b5b5bc14d41e66311ebcd9380db5840c022b3847ac`
- `test_collect.py`: `c4b94c4ca29a7ade909c8b69fe36c61d6d3099df124c7ee8339eb342703fd0b7`
- `test_profile_tools.py`: `26a3cb59a26008172c0ae834058b3e6d64e17abb9b5636815d2754aa57e61a86`

组合产物：private profile `ccedc155583d0f18e7d63d4e45e8dc2a80be8a910dc1e05924d8dceebbedfcdd`；
manifest `6a169d9e9e98be30149afbfae94ebb21422315574e7aba0d3a2ec3b18c892ab`；
public profile `890885818dae8c8f60e2f706958998838fcf63fc5c3a882d406f1f8ad04617a7`。

## 残余风险与证据边界

- Linux 的普通文件 symlink、真实 sysfs/权限、POSIX 进程组和公开输出 symlink 写入仍需 Linux 补跑；Windows junction 路径已覆盖。
- 路径检查与实际打开间仍存在并发替换 TOCTOU；公开产物中途 I/O 失败可能留下部分新 evidence。两项保留给复审判断，不宣称已消除。
- `host_test/pass` 不证明 Odin 3、CDSP/FastRPC/HTP、SDK 或游戏；`device_test` 与 `game_test` 均为 `not_run`。
