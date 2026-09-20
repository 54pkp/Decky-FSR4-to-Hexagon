# 当前状态与下一步

当前开发环境：**Windows；未连接 AYN Odin 3；只做理论、离线和 CPU 验证。**
目标设备仍为 Odin 3 / Snapdragon 8 Elite / Armada OS，实际镜像、ABI、HTP 和游戏均未验证。首个游戏未定，不阻塞下面的主机队列。

[首页](../README.md) · [轻量规则](ai/MULTI_AGENT_WORKFLOW.md) · [单次提示](ai/SINGLE_RUN_PROMPT.md) · [Goal 提示](ai/GOAL_PROMPT.md)

## 已有成果

M0 主机侧 schema、Linux 只读采集器、离线校验/脱敏、fixture 和 Python 回归已实现。
证据：[主机集成](validation/M0/2026-09-20-host-integration.md)、[修复报告](validation/M0/2026-09-20-review-fixes.md)、[定点复审](validation/M0/2026-09-20-first-batch-rereview.md)。
后续审计发现并修复了 public-v1 的路径豁免、序列号类型/拼写和任意 `value` 关系遍历问题；见 [脱敏边界加固](validation/host/2026-09-20-m0-redaction-hardening.md)。
已完成的 FIRST_BATCH 不重启。仓库没有可用的 FSR4 超分运行时、NPU 服务或 Decky 插件。

## 本阶段队列：Windows / CPU

这是独立的主机准备阶段，H 编号不代替 M0–M9。Goal 启动时冻结下表范围；完成后停止，设备验证留待用户提供环境后另开阶段。每行可拆成数个小批次，单次模式每次只做一批。

| 项目 | 产物与必需验收 | 依赖 | 进度 |
| --- | --- | --- | --- |
| H1 基线可复现 | 用仓库依赖在 Windows 运行现有 M0 unittest 和 fixture→validate→redact 最小链路；记录版本、准确命令、退出码与 skipped 原因。确保新检出无需私有目录。沿用已有工具，不重写框架 | 现有 M0 | complete |
| H2 元数据校验 | 小型离线 manifest/tensor 校验器与合成 fixture；检查必需字段、shape/dtype/layout、容量上限及非法元数据；真实资产未知可记录，不能伪造哈希或生产可用状态。合法样例通过、畸形输入确定性拒绝 | H1 | complete |
| H3 CPU 数值参考 | 小尺寸确定性数据，覆盖量化/反量化的舍入、饱和和误差，以及明确坐标/MV 方向的平移、重投影和 reset 样例；有独立手算/固定预期与声明容差。只验证选定算子，不称完整 FSR4 | H2 的数据约定 | complete |
| H4 同帧生命周期回放 | 一个 Windows CPU harness 使用 H2 输入和 H3 参考算子；同 context 单请求在途，核对 session/context/frame/history/model 身份，拒绝过期输出；reset/失败不污染 history，超时保留在途资源，显式完成后才能回收；成功与错误路径有自动检查 | H2 + H3 | in_progress |

边界：不在本阶段加入网络 daemon、完整 NGX DLL、真实 GPU/NPU 执行、Steam 安装器、Decky UI 或游戏兼容矩阵实现。允许为现有合同写最小 CPU 验证，不提前冻结未经设备证明的最终 ABI。实际 FSR4 权重 CPU 重放需要合法资产，作为后续可选实验，不是 H1–H4 的必需项。

**完成标准：** H1–H4 的实现、必需测试和短记录全部完成，实质代码/合同经过 Astra 审阅；已知仅适用 Linux/设备的检查列为后置，不能写成 pass。合成数值验证不能证明完整 FSR4、HTP 等价性、帧率、延迟或功耗收益。

## 当前接续点

- 下一批：修正中英文 README 的主机工具清单并提供统一 Windows 测试入口；随后继续 H4 的 timeout/pending consumption、history 提交和 reset/new generation 隔离。
- 当前最新记录：[M0 public-v1 脱敏边界加固](validation/host/2026-09-20-m0-redaction-hardening.md)。
- 设备、SDK、模型、首个游戏：当前均不要求提供。不要重复请求连接掌机或自动安装 WSL/Linux。
- 后续新增批次记录放 `docs/validation/host/`，本节保留最新链接和一个下一步，不累积长篇聊天摘要。

## 后置设备路线

M0 仍为 `in_progress`：现有 Windows 主机证据通过，设备/游戏检查 `not_run`。
M1–M9 仍为 `not_started`，各运行检查 `not_run`；H 队列推进不会自动改变这些门槛。
Linux 特有 symlink、进程组、SIGALRM、真实 sysfs/权限行为留待对应环境；Odin 3 的 M0-C 建档、QNN/HTP、游戏回写、画质和性能验证留待设备阶段。

详细技术条件按需查 [M0–M9 路线](roadmap/README.md)和[证据速查](ai/IMPLEMENTATION_GUIDE.md)；原始研究与历史报告保留原日期和结论。
