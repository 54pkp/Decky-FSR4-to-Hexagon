# M0 只读采集器主机验证

## 基本信息

```yaml
report_schema_version: draft-0
run_id: collector-host-20260920
milestone: M0
work_package: FIRST_BATCH-A-read-only-collector
source_commit: 91ae78e2042a4c8971b39a8abd381a0705ab7085
dirty_tree: true
started_at: 2026-09-20T07:42:35.6356567Z
finished_at: 2026-09-20T07:42:40.3000775Z
evidence_level: host_test
gate: pass
device_profile_id: device-c06864e341ed4397b305fcedb4f4e821 # fixture 产物，不是设备身份
model_manifest_id: null
service_instance_id: null
actual_backend: none
```

## 本次目标和适用范围

- 验证行为：冻结 CLI、Windows 上的 fixture 隔离运行、schema 兼容、超时子进程终止并回收、命令输出上限、已有输出拒绝覆盖、含空格显式路径和 manifest 哈希。
- 不覆盖：真实 Linux 文件超时行为、目标 Odin 3、CDSP/FastRPC/HTP、QNN、Steam/Proton 实际安装以及游戏运行。
- 依赖：`tools/device/schema/README.md` 和 `device-profile.schema.json` 的 `draft-0` 冻结合同；综合 fixture 和离线校验器由并行工作包提供。
- 目标环境：Windows 11 build 26200、AMD64、Python 3.12.7；没有目标设备访问。

## 环境与资产

| 项目 | 实际值及来源 |
| --- | --- |
| 主机、目标架构、OS/镜像/内核 | Windows NT 10.0.26200.0 / AMD64；仅主机 fixture 测试 |
| CPU/GPU/NPU、驱动、固件 | 未采集；不适用本主机测试 |
| libc、工具链、QAIRT/runtime | Python 3.12.7；QAIRT/runtime 未安装、未调用 |
| Steam/Proton/FEX/DXVK/vkd3d/Decky | 未运行；fixture 仅检查显式路径解析 |
| 模型/context/shader/输入序列 SHA-256 | 不适用 |
| 游戏构建与可执行文件哈希 | 不适用 |
| 仓库基线 | `91ae78e2042a4c8971b39a8abd381a0705ab7085`；共享工作区含并行未提交文件 |

## 检查记录

| 检查 ID | 层级 | 实际命令/操作 | 退出码 | 观察结果 | gate | 证据路径与哈希 |
| --- | --- | --- | --- | --- | --- | --- |
| A-SYNTAX | build | `python -m py_compile tools/device/collect.py` | 0 | Python 语法检查通过 | pass | `tools/device/collect.py`：`aea1576300eb3d5da0b42d54410571c132b8966747ea45250c5a18484da7a6fa` |
| A-HELP | host_test | `python tools/device/collect.py --help` | 0 | 冻结参数存在；帮助明确只读边界 | pass | `tools/device/README.md`：`67a2a747b5b0f154fd2272ed52b0cd14035e53c21b003ff472f703e336731f7d` |
| A-OFFLINE-SUITE | host_test | `python -m unittest discover -s tests/device -v` | 0 | 并行离线工具的 14 项合同测试通过；只作为本批接口兼容检查 | pass | 测试输出未单独落盘；测试源码归 Worker B |
| A-FIXTURE | host_test | `python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output $out` | 0 | 生成 fixture 私有档案；`example_only=true`、`gate=not_run`；未匹配 `uname`/`id` 为 `unavailable`，没有退回宿主执行 | pass | `%TEMP%/decky-final-f35e…/device-profile.json`：`a155ea980b241d0ed01dfe66599756927375620c494754e18f2a394ff1e3753f` |
| A-SCHEMA | host_test | `python tools/device/profile_tools.py validate (Join-Path $out "device-profile.json")` | 0 | 生成档案通过冻结 schema 及物理证据哈希校验 | pass | 同 A-FIXTURE |
| A-MANIFEST | host_test | 对 `run-manifest.json.artifacts` 逐项执行 `Get-FileHash -Algorithm SHA256` | 0 | 6 个 manifest artifact 的路径和 SHA-256 全部匹配 | pass | `%TEMP%/decky-final-f35e…/run-manifest.json`：`e4d026cd4dd9b377bc46bb658f774e1da18e2e0449831d7a17415663d8c80ee2` |
| A-FAILURES | host_test | 综合 fixture 注入空 stdout、60 秒延迟和退出码 7 | 0 | libc=`command_failed`、Vulkan=`timeout`（未等待 60 秒）、EGL=`command_failed`；其余采集继续 | pass | A-FIXTURE 的 profile/evidence |
| A-SPACES | host_test | `python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output $base --steam-path "/etc/path with spaces/example.conf" --proton-path "/etc/path with spaces/example.conf" --guest-exe "/etc/path with spaces/example.conf"` | 0 | 三个显式含空格路径保持原值；输出通过 schema 校验 | pass | 临时 fixture 输出，未提交 |
| A-OVERWRITE | host_test | 对 A-FIXTURE 的既有 `$out` 重复运行 collector | 2 | stderr 报告拒绝覆盖，既有输出不变 | pass | A-FIXTURE 输出 |
| A-UNSAFE | host_test | `python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output $bad --steam-path "../escape"` | 2 | 在创建输出前拒绝 fixture 路径逃逸；`$bad` 不存在 | pass | 命令输出未单独落盘 |
| A-TIMEOUT | host_test | Python REPL 调用 `ProductionRunner.run([sys.executable,'-c','import time; time.sleep(30)'],0.1)` | 0 | `timed_out=true`，子进程终止并已 `wait`，返回退出码 1 | pass | 主机控制台输出，未单独落盘 |
| A-BOUND | host_test | Python REPL 令子进程写出 1,048,593 bytes | 0 | 保存恰好 1,048,576 bytes，`stdout_truncated=true` | pass | 主机控制台输出，未单独落盘 |
| A-SAFETY-SCAN | source_review | `rg -n "shell\s*=\s*True\|os\.system\|sudo\|ssh\|subprocess\.(run\|call\|check_output)" tools/device/collect.py tools/device/README.md` | 1 | 无匹配；`Popen` 固定 `shell=False` | pass | `tools/device/collect.py` |
| A-DEVICE | device_test | 未执行 | null | 没有 Odin 3/Armada 设备访问 | not_run | 无 |
| A-GAME | game_test | 未执行 | null | 没有候选游戏或目标运行环境 | not_run | 无 |

## 正确性与失败路径

- fixture 的绝对 Linux 路径只映射到 `<case>/root`，命令必须与 `commands.json` 的 argv 数组精确匹配；未匹配项记录 `unavailable`，不执行 fixture 或宿主程序。
- 文件、目录、命令 stdout/stderr 均有大小或数量上限；Linux 主线程文件操作另有 `SIGALRM` 截止时间。该 Linux 文件截止机制未在 Windows 主机执行。
- 超时命令先 `terminate` 并 `wait`，必要时 `kill` 后再次 `wait`。本次只验证了 Windows 上的普通子进程回收，不代表设备 GPU/NPU 工作停止。
- 原始证据独立写入 `evidence/`，profile 引用安全相对路径、SHA-256、字节数和截断状态；manifest 哈希复核通过。
- 开发中曾发现 Windows 缺少 `grp/pwd` 的导入问题及一次语法错误；均已修复，以上表格记录修复后的最终检查。

## 结论与交接

- 主机工作包 gate 为 `pass`：采集器在现有综合 fixture 上产生可由冻结 schema 校验的输出，并覆盖关键安全/失败边界。
- 能证明：主机侧 CLI、fixture 隔离、结构化错误、证据/manifest、一部分 runner 超时与大小边界行为。
- 不能证明：真实 Linux sysfs/procfs 行为、实际设备身份、CDSP/FastRPC/HTP 可用性、QNN 或任何游戏链路。
- `device_test` 与 `game_test` 均为 `not_run`；M0 设备 gate 不应据此更新为通过。
- 未修改 schema、公共状态、fixture、测试或离线工具。
