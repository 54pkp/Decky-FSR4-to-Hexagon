# 当前状态与下一步

当前开发环境：**Windows；未连接 AYN Odin 3；只做理论、离线和 CPU 验证。**
目标设备仍为 Odin 3 / Snapdragon 8 Elite / Armada OS，实际镜像、ABI、HTP 和游戏均未验证。首个游戏未定，不阻塞下面的主机队列。

[首页](../README.md) · [轻量规则](ai/MULTI_AGENT_WORKFLOW.md) · [单次提示](ai/SINGLE_RUN_PROMPT.md) · [Goal 提示](ai/GOAL_PROMPT.md)

## 已有成果

M0 主机侧 schema、Linux 只读采集器、离线校验/脱敏、fixture 和 Python 回归已实现。
证据：[主机集成](validation/M0/2026-09-20-host-integration.md)、[修复报告](validation/M0/2026-09-20-review-fixes.md)、[定点复审](validation/M0/2026-09-20-first-batch-rereview.md)。
后续审计发现并修复了 public-v1 的路径豁免、序列号类型/拼写和任意 `value` 关系遍历问题；见 [脱敏边界加固](validation/host/2026-09-20-m0-redaction-hardening.md)。
已完成的 FIRST_BATCH 不重启。仓库没有可用的 FSR4 超分运行时、NPU 服务或 Decky 插件。

## 已完成阶段：H1–H4 Windows / CPU

这是已完成的第一阶段主机准备工作，H 编号不代替 M0–M9。保留其验收范围与历史证据；后续单次开发从下面的 P 队列选择，不重启 H 项。

| 项目 | 产物与必需验收 | 依赖 | 进度 |
| --- | --- | --- | --- |
| H1 基线可复现 | 用仓库依赖在 Windows 运行现有 M0 unittest 和 fixture→validate→redact 最小链路；记录版本、准确命令、退出码与 skipped 原因。确保新检出无需私有目录。沿用已有工具，不重写框架 | 现有 M0 | complete |
| H2 元数据校验 | 小型离线 manifest/tensor 校验器与合成 fixture；检查必需字段、shape/dtype/layout、容量上限及非法元数据；真实资产未知可记录，不能伪造哈希或生产可用状态。合法样例通过、畸形输入确定性拒绝 | H1 | complete |
| H3 CPU 数值参考 | 小尺寸确定性数据，覆盖量化/反量化的舍入、饱和和误差，以及明确坐标/MV 方向的平移、重投影和 reset 样例；有独立手算/固定预期与声明容差。只验证选定算子，不称完整 FSR4 | H2 的数据约定 | complete |
| H4 同帧生命周期回放 | 一个 Windows CPU harness 使用 H2 输入和 H3 参考算子；同 context 单请求在途，核对 session/context/frame/history/model 身份，拒绝过期输出；reset/失败不污染 history，超时保留在途资源，显式完成后才能回收；成功与错误路径有自动检查 | H2 + H3 | complete |

边界：不在本阶段加入网络 daemon、完整 NGX DLL、真实 GPU/NPU 执行、Steam 安装器、Decky UI 或游戏兼容矩阵实现。允许为现有合同写最小 CPU 验证，不提前冻结未经设备证明的最终 ABI。实际 FSR4 权重 CPU 重放需要合法资产，作为后续可选实验，不是 H1–H4 的必需项。

**完成标准：** H1–H4 的实现、必需测试和短记录全部完成，实质代码/合同经过 Astra 审阅；已知仅适用 Linux/设备的检查列为后置，不能写成 pass。合成数值验证不能证明完整 FSR4、HTP 等价性、帧率、延迟或功耗收益。

## 当前阶段队列：P1–P9 无设备准备

本阶段由用户授权新增。详见[进展评估、材料清单和分批验收](roadmap/HOST_PREPARATION.md)。P1–P2 与 P9a–P9c 已完成，后续按依赖逐批实施；设备与游戏仍 `not_run`。

执行约定：个人本地实验、先跑通；FSR 材料允许使用可核对内容的公开 fork/镜像，仅保留必要来源/版本/完整性记录和随包通知，不另做许可审计批次。NPU 量化目标为 W8A8，与 INT8 类型不互斥；是否转换/重新量化由实际 encoding 和工具链决定。模型/SDK 不随源码提交。

| 批次 | 小批次产物 | 依赖/阻塞 | 进度 |
| --- | --- | --- | --- |
| P1 Windows 环境入口 | 显式解释器、隔离 venv、版本/架构预检与新环境复现 | 无 SDK/模型依赖 | complete |
| P2 外部资产核验 | 来源/版本/哈希登记、随包通知、只读核验与合成测试 | P1；不改 H2 synthetic 合同 | complete |
| P3 QAIRT 本地准备 | 官方 SDK、独立环境、Windows 工具冒烟和能力表 | P1/P2；合法包、登录和版本条件 | not_started |
| P4 ABI 离线检查 | PE/ELF 解析、目标库候选清单、错误输入测试 | P2；真实清单需 P3，合成测试可先做 | not_started |
| P5 自有小图 CPU 基准 | 小型 ONNX、三类输入、独立预期与明确容差 | P1/P2；无 SDK/模型依赖 | complete |
| P6 小图 QAIRT 转换 | W8A8 转换/量化、实际 encoding 检查、产物与日志绑定 | P3/P5；HTP prepare 条件不足可后置 | not_started |
| P7 FSR v07 提取 | 匹配源材料接收、提取封装和上游交叉自检 | P2；必须取得并核验具体 AMD 文件 | not_started |
| P8 FSR 子图 CPU 对照 | 真实提取结果的 simulator/ONNX 对照与误差记录 | P7/P5；不声称官方完整等价 | not_started |
| P9a 资源预算 | 隔离资源上限、背压与完成后回收 | H4；无 SDK/模型依赖 | complete |
| P9b 幂等保留 | 去重记录上限、过期通知拒绝与重试语义 | P9a；无 SDK/模型依赖 | complete |
| P9c 失败/关闭 | 最小故障/关闭事件、候选 history 与迟到完成测试 | P9a/P9b；无 SDK/模型依赖 | complete |

选取规则：优先 P1，然后按依赖选一批；资产阻塞只暂停相应分支，可继续 P4 合成部分、P5 或 P9 子批次。P1–P8 加 P9a/P9b/P9c 共 11 个单次批次。每批必须有实际实现/检查和短记录；不能以说明书或 mock 代替真实资产安装、转换或推理的验收。P 队列不包含 Linux/WSL 安装或设备部署。

## 当前接续点

- H1–H4 Windows / CPU 队列已完成；这不改变后置 M0–M9 的设备门槛。
- 下一批：P4，先交付自有合成 PE/ELF 解析与错误输入检查；在取得 P3 的合法 QAIRT 包和候选库清单前保持 `in_progress`，不推断目标 ABI 兼容。P3 仍等待合法包条件。
- 当前最新记录：[P5 自有小图 CPU 数值基准](validation/host/2026-09-21-p5-onnx-cpu-reference.md)；阶段规划见[无设备阶段二规划](validation/host/2026-09-20-host-preparation-plan.md)。
- 设备与首个游戏不阻塞 P 队列。SDK/模型只在对应资产批次需要；缺少时推进独立分支，不重复请求掌机或自动安装 WSL/Linux。
- 后续新增批次记录放 `docs/validation/host/`，本节保留最新链接和一个下一步，不累积长篇聊天摘要。

## 后置设备路线

M0 仍为 `in_progress`：现有 Windows 主机证据通过，设备/游戏检查 `not_run`。
M1–M9 仍为 `not_started`，各运行检查 `not_run`；H 队列推进不会自动改变这些门槛。
Linux 特有 symlink、进程组、SIGALRM、真实 sysfs/权限行为留待对应环境；Odin 3 的 M0-C 建档、QNN/HTP、游戏回写、画质和性能验证留待设备阶段。

详细技术条件按需查 [M0–M9 路线](roadmap/README.md)和[证据速查](ai/IMPLEMENTATION_GUIDE.md)；原始研究与历史报告保留原日期和结论。
