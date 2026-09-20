# FIRST_BATCH targeted Astra re-review packet

## 精确范围

- 初审 verdict：`change`，冻结 Head `6e4e6c87c51b33b1ef85b8bcd63e4904125d07af`。
- 修复 Head：`5c5775be613a37c81c1d3f6a2552f6951d3bb56e`。
- 只审命令：

```text
git diff --find-renames 6e4e6c87c51b33b1ef85b8bcd63e4904125d07af..5c5775be613a37c81c1d3f6a2552f6951d3bb56e -- tools/device/collect.py tools/device/profile_tools.py tests/device/test_collect.py tests/device/test_profile_tools.py docs/validation/M0/2026-09-20-review-fixes.md
```

本包自身在修复 Head 后创建，不在复审 diff。完整初审包与原始范围见
`docs/validation/M0/2026-09-20-first-batch-review.md`；不要求重读未受影响的 schema、fixture 或 worker 历史。

## 五项发现与对应修复

| 初审发现 | 修复符号/测试 |
| --- | --- |
| P1 fixture root/commands 逃逸 | `FixtureRunner.__init__`、`Collector.__init__/system_path`；`test_fixture_root_link_cannot_escape_case`、commands link 测试（Windows skip） |
| P1 descendant pipe timeout 卡死 | `ProductionRunner.run`、`_terminate_process_tree`；`test_descendant_inheriting_pipes_cannot_extend_timeout_indefinitely` |
| P1 public-v1 路径/serial/文件名泄露 | `_sensitive_tokens`、`_redact_tree`、public evidence ID mapping；spaced path/serial/private basename 测试 |
| P2 username 污染 `user_input` | `REDACTION_PRESERVED_KEYS`；common username protocol test |
| P2 public evidence 写出逃逸 | `redact_profile` resolved output containment；public evidence junction 测试 |

## 复审证据

- 报告：`docs/validation/M0/2026-09-20-review-fixes.md`。
- `python -m unittest discover -s tests/device -v`：exit 0；28 项，26 pass、2 skip。
- skip：Windows 普通文件 symlink 权限（commands.json/evidence file）；Windows junction 的 fixture root 与 public output destination 均已真实执行并通过。
- 修复后 A→B CLI 往返：collect/private validate/redact/public validate 全部 exit 0；public evidence 5 项。
- Windows Job Object 回归同时断言 leader 正常退出后 30 秒后代 PID 不存活、collector reader 线程清零。
- `.json` evidence 使用结构化脱敏；缺失 fixture `commands.json`/`root` 的 CLI 均返回 2。
- Windows 实际命令由 wrapper 在 Job attach 前阻塞；延迟 attach 时未提前启动，attach 失败时不执行。JSON evidence 不应用 profile 协议字段豁免。
- 真实 Linux、Odin 3 device_test、game_test 仍为 `not_run`。

## 要求裁决

- 只判断五项发现是否关闭及修复是否引入连带正确性问题。
- 输出 `review_verdict=pass/change/blocked`、具体残余风险、精确未运行项。
- device gate 必须独立，保持 `not_run`；复审 pass 不等于设备验证。

## 最终裁决

- 审阅者：项目 `fsr4_reviewer`（GPT-6 Astra / high）。
- `review_verdict=pass`，仅适用于 Head `5c5775be613a37c81c1d3f6a2552f6951d3bb56e` 的声明修复范围。
- JSON evidence 的协议豁免泄露与 Windows Job attach 竞态均已关闭；未发现修复增量的阻断性连带问题。
- 残余风险：路径检查/open 的 TOCTOU；公开写入失败后的部分产物残留。
- 未运行：Linux 普通文件 symlink、POSIX 进程组、SIGALRM、真实 sysfs/权限；Windows 两项普通文件 symlink 测试因权限 skip。
- `device gate=not_run`；`game gate=not_run`。本裁决不是 M0 设备验证。
