# FIRST_BATCH Worker A 交接：M0 只读采集器

## 当前现场

- 工作包：`docs/ai/FIRST_BATCH.md` 的 A 卡；日期 2026-09-20。
- owner/角色：Worker A，GPT-5.6 Sol / medium。
- 基线：`91ae78e2042a4c8971b39a8abd381a0705ab7085`；共享工作区有 Worker B 的未提交文件，本工作包未修改它们。
- 本工作包独占文件：`tools/device/collect.py`、`tools/device/README.md`、本报告和本交接。
- 环境：Windows 11 / AMD64 / Python 3.12.7；无目标设备访问、无设备凭证。
- 目标：实现冻结 `draft-0` 合同的 Linux 普通用户只读采集器和 fixture runner，不进行安装、提权、系统修改、远程登录或 DSP 会话。

## 已完成的变化

| 文件/模块 | 行为变化 | 验证报告 |
| --- | --- | --- |
| `tools/device/collect.py` | 新增冻结 CLI、生产/fixture runner、超时与输出上限、Linux 身份/OS/SoC/remoteproc/节点元数据/图形栈采集、显式 ELF/PE 路径检查、证据与 manifest 生成 | [collector validation](2026-09-20-collector.md) |
| `tools/device/README.md` | 记录使用方式、只读边界、fixture 隔离、退出码和不能证明的范围 | [collector validation](2026-09-20-collector.md) |

## 尚未完成或验证

- `device_test: not_run`：没有在 Odin 3/Armada 或其它 Linux 目标上运行。
- `game_test: not_run`：没有实际 Steam/Proton/guest 游戏链路。
- Linux `SIGALRM` 文件读取超时、真实 sysfs symlink、字符设备权限元数据尚未在 Linux 验证。
- 没有打开 FastRPC/dma-heap 节点、DSP/HTP 会话；这属于明确安全边界，不是缺陷。
- 没有实现或修改脱敏/校验器、fixtures、tests、schema、requirements 或公共状态。

## 决定与合同

- CLI、fixture `commands.json` 和 runner 结果严格沿用 S0，无合同或 schema 变更。
- fixture 模式中，Linux 绝对路径映射到 case 的 `root/`；命令只读取精确 argv 对应的预录制文件。未匹配命令为 `unavailable`。
- 普通命令成功但 stdout 为空记为 `command_failed`；存在但不可执行或 stderr 明确 permission denied 记为 `permission_denied`。
- remoteproc 按所有可见 `remoteproc*` 名称枚举，并由可观察 `name` 中的 `cdsp` 标注候选；不固定编号。
- FastRPC/dma-heap 仅 `lstat` 元数据，不打开节点。显式二进制仅读取 4096-byte 头并记录 ELF/PE 架构证据。
- 采集器输出始终是 private；公开输出只能由离线脱敏入口生成。
- 无 ADR；没有改变共享 `draft-0` 语义。

## 复现与恢复

- 工作目录：仓库根目录。
- 最短成功检查：

```text
python -m py_compile tools/device/collect.py
python tools/device/collect.py --help
python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output <new-temp-dir>
python tools/device/profile_tools.py validate <new-temp-dir>/device-profile.json
python -m unittest discover -s tests/device -v
```

- 最终 fixture profile SHA-256：`a155ea980b241d0ed01dfe66599756927375620c494754e18f2a394ff1e3753f`；manifest SHA-256：`e4d026cd4dd9b377bc46bb658f774e1da18e2e0449831d7a17415663d8c80ee2`。临时目录位于 `%TEMP%/decky-final-f35e…`，不是持久仓库证据。
- 代码 SHA-256：collector `aea1576300eb3d5da0b42d54410571c132b8966747ea45250c5a18484da7a6fa`；README `67a2a747b5b0f154fd2272ed52b0cd14035e53c21b003ff472f703e336731f7d`。
- 输出目录必须是新路径；恢复/重跑请改用另一个新目录，不删除或覆盖旧目录。

## 下一位应当做什么

1. Integrator 检查 A/B 实际 diff，并用 B 的 schema validator 验证 A 的新 fixture 输出。
2. 在 Linux 主机（仍非目标设备也可）补跑真实文件、目录和子进程边界，核对 `SIGALRM`、sysfs symlink 与权限分类。
3. 有设备所有者明确授权后，才在目标设备运行 collector 并人工复核身份、remoteproc、FastRPC/dma-heap 和图形信息；仍不得把这些结果称为 HTP 执行。
4. 仅 integrator 更新公共状态；不要覆盖 Worker B 的 fixture/tests/profile_tools 变化。

## 可直接发送的后续任务

```text
请集成 FIRST_BATCH Worker A 的只读采集器，先读 AGENTS.md、docs/ai/FIRST_BATCH.md、
docs/validation/M0/2026-09-20-collector-handoff.md 和实际 A/B diff。保持冻结 draft-0
合同，运行综合 fixture、schema 校验、覆盖拒绝、超时回收、证据哈希与路径逃逸检查。
没有目标设备时保持 device_test/game_test 为 not_run，不把 fixture 或 Windows 结果扩写为
Odin 3、CDSP、FastRPC 或 HTP 验证。
```
