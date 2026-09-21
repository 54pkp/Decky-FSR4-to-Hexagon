# 首批开发卡：M0 主机侧只读设备建档

状态：**主机侧已完成并通过定点 Astra 复审；目标设备验证仍为 `not_run`。** 实现、集成与复审证据见 `docs/validation/M0/`；本卡保留为首批工作的历史范围，不再作为下一轮 Goal 的起点。

归档阅读说明（2026-09-22）：下文角色卡、强制多报告与启动提示保留原始历史，不覆盖[当前轻量流程](MULTI_AGENT_WORKFLOW.md)。后续审计欠账已列入[无设备新批次](../roadmap/HOST_PREPARATION.md)，下一步查[STATUS](../STATUS.md)；历史复审通过不表示这些残余风险已关闭。

## 目标与边界

交付一个最小、可审阅的设备报告 schema，以及只读采集、离线校验和公开脱敏路径。先由一位 Sol integrator 串行冻结约定，再让两位 Sol 在不重叠的文件范围内并行实现，最后由 integrator 集成主机测试并交给 Astra 集中审阅。

本批不安装 QNN/驱动，不打开 DSP 会话，不使用或保存 SSH 凭证，不扫描整份家目录，不修改 Steam/系统配置，不提权、不刷固件、不改设备树、不运行 RP6 解锁步骤。采集器只写调用者显式指定的新输出目录；设备上运行属于后续 M0-C，未获真实输出前不得声称 Odin 3、CDSP、FastRPC、HTP 或游戏链路可用。

以下路径是本批计划时冻结的范围，目前实现已存在；后续任务必须先检查工作树和真实 diff。`draft-0` 核心语义继续以 `docs/architecture/CONTRACTS.md` 为准，本批只把 M0 报告的最小字段、来源和错误表达落成 schema，没有扩展到帧协议、生命周期、统一错误枚举或其它节点合同。

## 分角色小读取包

不要让所有角色重复读取同一整包。S0 integrator 读 `AGENTS.md`、本卡、`docs/STATUS.md`、`docs/architecture/CONTRACTS.md` 第 2、3、7、9 节及 M0 第 1、2、4–6、8、9 节。A 只补读 S0 产出的 schema/说明、M0 第 2、4、5（M0-B）、7、8 节。B 只补读 S0 产出的 schema/说明、合同第 2、3、9 节及 M0 第 2、5（M0-A）、6、8 节。集成者读取 A/B 的短 handoff、实际 diff 和测试输出；Astra 读取冻结后的 review packet。各角色复用 README 的公开范围，不复制大段原文。

## S0：Sol integrator 串行冻结最小约定

依赖：无。并行任务 A/B 必须等待此卡合入共同基线。

拟议独占文件：

- `tools/device/schema/device-profile.schema.json`
- `tools/device/schema/README.md`
- `tools/device/requirements-host.txt`
- `docs/validation/M0/<date>-schema-contract.md`
- `docs/validation/M0/<date>-schema-contract-handoff.md`

工作：

1. 固定 `schema_version: "draft-0"` 的 M0 报告形状，不改变共享 draft-0 核心协议；定义 `example_only`、`device_profile_id`、`supersedes`、`evidence_level`、`gate`、采集时间/方法、工具 commit 和硬件/OS/图形/NPU 基础/运行栈/游戏候选对象。
2. 观察项至少能表达 `value`、`source`、`observed_at`、`status` 和未知/失败原因；允许 `null`，区分 `missing`、`unavailable`、`permission_denied`、`timeout`、`command_failed` 与成功，保留命令退出码和截断后的 stderr，禁止把缺项推断为“不支持”。
3. 固定原始证据引用格式：相对输出目录的安全路径、采集项 ID、SHA-256、字节数与是否截断；schema 不内嵌凭证或无限长命令输出。
4. 固定 collector 输出：显式新目录内至少包含私有 `device-profile.json`、`evidence/` 与 `run-manifest.json`；公开报告只能由后续脱敏步骤产生。已有目录或文件默认拒绝覆盖。
5. 写清 `gate` 与字段 `status` 不互相替代；示例只能 `example_only: true`，主机测试只能证明工具行为，不能把 `device_test` 写成 `pass`。
6. 区分两种版本：拟采用 JSON Schema Draft 2020-12，报告内 `schema_version: "draft-0"` 是本项目数据合同版本。实施时核对 `jsonschema` 官方文档及 Python 兼容性，锁定支持该规范的具体版本写入 `requirements-host.txt`，再固定 `$schema` 与 validator；依赖缺失时明确失败，不静默降级为不完整自制校验器。
7. 冻结 CLI：collector 为 `python tools/device/collect.py --output <new-dir>`，可选显式 Steam/Proton/guest 路径参数与仅测试用 `--fixture-root <case-dir>`；离线工具为 `python tools/device/profile_tools.py validate <profile> [--schema <schema>]` 和 `... redact <private-profile> --output <new-public-profile>`，未传 `--schema` 时使用仓库固定 schema。退出码统一为：`0` 完成（字段级采集失败仍写入报告）、`1` profile/schema 校验不通过、`2` CLI/输入/拒绝覆盖错误、`3` 无法产出可信报告的内部或 I/O 致命错误；诊断写 stderr，数据只写指定文件。
8. 冻结 fixture 布局：每个 `<case-dir>` 含 `root/`（镜像 `/etc`、`/proc`、`/sys`、`/dev` 的相对树）、`commands.json`、`command-output/` 和 `expected/device-profile.json`，脱敏用例可另含 `private-profile.json` 与 `expected/public-profile.json`。`commands.json` 是记录数组；每项以 `argv` 字符串数组精确匹配，并只描述 `available`、`exit_code`、`stdout_file`、`stderr_file`、`delay_ms`。fixture 输入引用均为 case 内无 `..` 的相对路径；新生成的证据写入调用者指定的新输出目录。fixture 模式不得执行 fixture 内程序；未匹配 argv 按 command missing 记录。生产模式只通过同一 runner 接口调用 `subprocess`，从而允许 B 的固定数据注入而不复制 A 的解析逻辑。

验收：A/B 可仅凭 schema README 独立实现；schema 可被 Draft 2020-12 metaschema 检查，CLI/退出码、fixture 和命令 runner 协议无歧义；没有真实设备值、伪版本号或 SSH 字段。S0 只在实际完成后写自己的 validation/handoff，不代写 A/B 报告。若发现必须改变共享合同，暂停并按 ADR 流程另开工作包，不在本批暗改。

## A：Sol 并行卡——Linux 只读采集与错误记录

依赖：S0。拟议独占文件：

- `tools/device/collect.py`
- `tools/device/README.md`
- `docs/validation/M0/<date>-collector.md`
- `docs/validation/M0/<date>-collector-handoff.md`

工作：

1. 用 Python 3 标准库实现普通用户只读采集；文件读取与外部命令均有超时/大小上限，外部命令使用 argv 数组且不经 shell。
2. 采集 uname、os-release、glibc、device-tree model/compatible、可读 SoC 字段；枚举全部 remoteproc 后按可观察名称标注 CDSP 候选，不固定 `remoteproc0`。
3. 只记录 FastRPC/dma_heap 节点元数据和权限，不打开节点；仅在已安装时调用 `bootc`、`vulkaninfo`、`eglinfo`，各失败独立记录，不中断其余采集。
4. Steam、Proton 和 guest EXE 只检查用户显式传入的路径；记录 ELF/PE 架构证据，不扫描账户、不读取令牌、不由进程名推断 ABI。
5. 对缺文件、不可读、权限不足、命令缺失、非零退出、超时和输出截断生成 S0 约定的结构化结果；路径含空格时行为一致。
6. CLI 默认只读，要求显式输出目录且拒绝覆盖；帮助文本明确它不会安装、提权、刷写、解锁、修改配置或远程登录。

交付标准：能按 S0 的 fixture 根目录/命令替身协议运行并留下原始证据映射；不得包含真实设备输出、硬编码个人路径或“HTP 已验证”结论。A 不创建 fixture，也不编写 B 的预期结果；A 只写自己的 collector validation/handoff，记录实际自检与未运行项。

## B：Sol 并行卡——离线 fixture、校验、脱敏与测试

依赖：S0。拟议独占文件：

- `tools/device/profile_tools.py`
- `tools/device/fixtures/**`
- `tests/device/**`
- `docs/validation/M0/<date>-offline-tools.md`
- `docs/validation/M0/<date>-offline-tools-handoff.md`

工作：

1. 实现离线 schema 校验和确定性的公开脱敏入口；输入/输出均为显式文件，默认拒绝覆盖，不依赖设备、网络或专有 SDK。
2. fixture 至少覆盖：完整匿名示例、无 Steam、权限受限、命令缺失、超时、非零退出、空文件、输出截断、路径含空格、损坏证据引用和未知额外字段策略；全部标 `example_only: true`、`gate: not_run`。
3. 脱敏用户名、主机名、家目录/个人路径、序列号式标识和命令输出中的同类片段；保留诊断需要的架构、版本、状态、错误类别、哈希与来源关系。对脱敏后的证据重新计算哈希并区分原始/公开产物；不公开的原始证据标明未附带，不将已修改文本与原始哈希搭配冒充同一文件。测试公开输出中不存在 fixture 注入的敏感哨兵。
4. 校验失败必须指出稳定的字段路径和原因；测试拒绝缺少版本/ID/来源、非法 gate/evidence level、绝对 evidence 路径、路径逃逸、哈希格式错误和示例冒充实测。
5. 通过手工构造的预期文档与畸形输入验证合同，不能导入 A 的内部解析函数来重新计算所有预期值；至少一组 golden fixture 独立于 A 的实现。

交付标准：测试可在无设备环境运行，fixture 无个人信息；校验/脱敏结果不能证明采集器或硬件通过。B 只写自己的 offline-tools validation/handoff，报告 `jsonschema` 实际版本和独立 golden fixture 的来源。

## I：Sol integrator 集成与主机验证

在 A/B 都完成后串行合并，先检查 `git diff` 和文件归属；解决接口偏差时优先保持 S0，必要修改必须同步生产者、消费者与测试。集成者独占 `docs/validation/M0/<date>-host-integration.md`、`docs/validation/M0/<date>-host-integration-handoff.md` 和该批 review packet；只在已实际运行后创建，沿用仓库模板，记录命令、退出码、环境、commit、产物哈希和未运行项。此时最多可报告 `host_test/pass`，M0 节点仍不能标完成。

拟议验证命令（不是已执行记录，具体入口以实现帮助文本为准）：

```text
python -m json.tool tools/device/schema/device-profile.schema.json
python tools/device/profile_tools.py validate tools/device/fixtures/<case>/expected/device-profile.json
python -m unittest discover -s tests/device -v
python tools/device/collect.py --help
python tools/device/collect.py --fixture-root <fixture-root> --output <new-temp-dir>
python tools/device/profile_tools.py validate <new-temp-dir>/device-profile.json
python tools/device/profile_tools.py redact <private.json> --output <new-public.json>
```

集成检查必须覆盖拒绝覆盖、超时后进程处置、证据哈希、目录逃逸、空格路径、错误仍可追溯、脱敏哨兵消失，以及 A 的输出能被 B 校验；不能只跑 happy path。真实 Linux 行为与设备运行未执行时分别写 `not_run`，不得用 Windows/fixture 结果代替。

## R：每批一次 Astra 集中审阅

本批集成主机检查有完整结果后，冻结审阅对象并由 Astra 做该批的一次集中审阅，减少上下文重复。审阅输入限于 review packet、精确最终 diff、测试输出及各 validation/handoff；重点核查只读边界、draft-0 一致性、生产者/消费者契合、错误证据、脱敏遗漏、fixture 独立性和证据等级。Astra 给出按严重度排序的具体问题；integrator 定点修复并只重跑受影响检查，随后 Astra 复审修复 diff 与连带影响，无需重读整批历史。新增架构变化或审阅对象实质扩张时重新冻结并按新批次集中审阅。Astra 审阅本身不是设备验证，也不批准进入刷机或固件修改。

## 后续并行准备与不可跳过的门槛

- M1：可并行准备 provider 枚举/错误归类、ABI/动态库诊断和离线 CLI 测试；开始真实 QNN/HTP 图执行前，必须取得 M0 真实设备档案、Linux glibc ARM64 兼容的已授权 QAIRT/runtime、可观察 CDSP/FastRPC 与明确权限。CPU/mock/QNN CPU 不算 HTP。
- M2：可并行整理模型来源/许可、manifest schema、tensor/量化元数据校验、GPU 前后处理参考与离线向量；宣称移植成功前必须锁定模型/工具/runtime 哈希，并在目标 GPU/HTP 路径核对 tensor、量化和输出，不能用 XLSR/CAS/双线性结果替代 FSR4。
- M3：可并行做 PE/ELF 检查器、NGX ABI 探针设计、可重复游戏场景与日志格式；注入/加载或游戏验证前必须确认候选游戏、图形 API、guest PE 架构、Proton/FEX 加载链和可回滚基线。没有候选游戏不阻塞 M1，但不能越级形成游戏兼容结论。

## 历史启动提示

以下提示仅记录首批任务的原始派工方式；该批已经完成，不应再次作为长期 Goal 启动。继续开发请使用 [GOAL_PROMPT.md](GOAL_PROMPT.md)。

> 在 Decky FSR4 to Hexagon 仓库执行 `docs/ai/FIRST_BATCH.md` 的首批 M0 主机侧工作。先让一位 Sol integrator 完成并冻结 S0 的 schema、CLI、fixture/命令替身和校验依赖；S0 合入共同基线后，再按各自小读取包并行派两位 Sol 执行 A 与 B，严格遵守互不重叠的源码、测试和报告路径。两者完成后由 integrator 串行集成并运行拟议主机检查，保存真实命令、退出码和未运行项；冻结 review packet 后交给 Astra 做本批集中审阅，Sol 定点修复，Astra 按影响范围复审。不要改 draft-0 核心协议，不使用 SSH 凭证，不安装/提权/刷固件/修改系统，不创建虚假设备输出；无 Odin 3 实测时保持 `device_test: not_run`，不要把 M0 标为通过。
