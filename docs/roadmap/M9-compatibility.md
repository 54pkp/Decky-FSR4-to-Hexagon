# M9：兼容性扩展与后续输入适配

> 状态：路线设计；OptiScaler Hexagon 后端、新的 D3D12/Vulkan 接入和原生 FSR API 适配均未实现。原生 FSR 仅建立专项入口，不在本节点提前展开深度研究。

先读 [AI 实施指南](../ai/IMPLEMENTATION_GUIDE.md)、[公共合同](../architecture/CONTRACTS.md)、[M3](M3-game-probe.md)、[M5](M5-temporal-quality.md)、[M6](M6-performance.md) 与 [项目状态](../STATUS.md)。若相关文档的实际文件名调整，以路线索引为准。

## 1. 目标与范围

目标是在一个游戏/一个 API 的正确性和性能已被证明后，有控制地增加游戏、图形 API、代理 ABI 和输入前端；每个新增组合留下可重复证据。

兼容性单位不是“游戏名”，而是游戏构建、入口 API、代理 ABI、Proton/FEX/DXVK/vkd3d、驱动、设备、模型和 mode 的组合。一个组合成功不得自动推广到其它组合。

本节点工作包可择一推进：新增同 API 游戏 profile、OptiScaler 自定义后端、D3D12、Vulkan、原生 FSR API 可行性入口。不要同一批次同时换输入 API、模型和同步架构。

非目标：DLSS Frame Generation、Ray Reconstruction、Reflex、全部 NVIDIA 能力仿真、通用反作弊绕过、仅靠 present 色彩帧重建完整 FSR4 时序输入。

## 2. 依赖与无设备工作

- 新游戏/后端发布资格依赖 M5 + M6；M7 profile 与恢复机制应先稳定，再向用户分发扩展。
- 新图形 API 必须重新经过 M3→M4→M5→M6 对应测试，不继承 D3D11 的资源同步结论。
- 无设备可审计固定源码、实现接口骨架、最小 API 样例和协议 fixtures；不能标某游戏已支持。
- 需要专有游戏/SDK/模型时先列来源与现有授权，准备独立合成 harness，缺资产不阻塞可做的接口工作。
- 首个新增目标由实际游戏可运行性、可重复场景和合法可用资产决定，不仅按知名度选择。

## 3. 固定源码参考

- [fsr4-hexagon NGX 实现](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/full_proxy.c)：D3D11 闭环是可审阅起点，D3D12 返回不支持不能被文件名掩盖。
- [特定游戏注入器](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/injector/d3d12_inject.c)：注册表注入不是 D3D12 资源执行支持。
- [OptiScaler 固定版本 README](https://github.com/optiscaler/OptiScaler/blob/93fbf1b2696112945f87d8a2cea9bdada5720d25/README.md)、[Linux setup](https://github.com/optiscaler/OptiScaler/blob/93fbf1b2696112945f87d8a2cea9bdada5720d25/setup_linux.sh)、[LICENSE](https://github.com/optiscaler/OptiScaler/blob/93fbf1b2696112945f87d8a2cea9bdada5720d25/LICENSE)：需新增后端，不是现成 NPU 开关；该快照为 GPL-3.0。
- [fork Vulkan present 路线](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/layer/src/layer_entry.cpp)：参考资源生命周期，不能从 present hook 推断已获得 MV/jitter/depth。
- [Microsoft D3D12 同步说明](https://learn.microsoft.com/en-us/windows/win32/direct3d12/executing-and-synchronizing-command-lists)：在线规范，实施时记录读取日期。
- [AMD FSR API 官方入口](https://gpuopen.com/manuals/fsr_sdk/getting-started/ffx-api/)：用于将来专项研究，实施时锁定实际 SDK tag/hash，不能把在线最新 ABI 当所有游戏 ABI。

引用固定快照与实现时选用的新版本要分别记录；更换依赖需 ADR，不静默升级整条链。

## 4. 建议模块与兼容性登记

```text
adapters/optiscaler/              # 上游补丁/自定义后端，不复制整仓而不标来源
adapters/ngx/d3d12/               # 命令提交、状态和输出生命周期
adapters/ngx/vulkan/              # Vulkan NGX 调用边界适配
adapters/fsr/                     # 后续专项批准后才建立实现
profiles/<appid>/<variant>.json   # 同一游戏允许多个明确变体
tests/graphics/d3d12/             # 最小提交、队列与失效样例
tests/graphics/vulkan/            # 队列、layout、ownership 样例
docs/compatibility/               # 变体矩阵、限制、回归策略
docs/validation/M9/               # 日期-工作包.md 与 -handoff.md
```

拟议变体键包括 `game_build`、`graphics_api`、`adapter_abi`、`input_frontend`、`proton_version`、`translator_version`、`graphics_bridge_version`、`device_profile_id`、`model_manifest_id`、`mode`。

`appid` 不能替代安装来源和构建身份；非 Steam 游戏用显式本地标识，不编造 Steam AppID。每行记录具体限制、最后验证日期与报告链接。

## 5. 分批工作包

### M9.A 新增同 API 游戏

1. 先证明原游戏在目标兼容栈稳定运行；记录无本项目基线和可重复场景。
2. 用 M3 探针确定加载 DLL、导出、PE ABI、NGX feature 和真实 Evaluate，而非仅检查 DLSS 菜单。
3. 比较运动矢量单位/方向、jitter、曝光、depth、reset、资源格式和尺寸；不同语义写为显式适配。
4. 以 M4 同帧路径接通，完整执行 M5 场景切换与故障，再做 M6 热稳态与延迟。
5. 仅写入该变体 profile；安装/恢复和与已知 mod 冲突行为由 M7 验证。

输出最小新增 profile、对应输入语义表、图像/trace 索引和准确支持范围。未测 HDR/DRS 继续拒绝，不能因为新游戏有该选项就开放。

### M9.B OptiScaler 自定义 Hexagon 后端

1. 克隆并固定计划采用的上游 SHA，列清后端抽象、资源所有权、capability 查询、UI 配置与 fallback 路径。
2. 先用 dummy backend 验证正常生命周期、错误传播和每个 context 隔离，不能以 dummy 输出通过游戏支持门槛。
3. 定义名为 `FSR4-Hexagon` 的明确后端能力，将规范化输入映射至公共帧协议；不复用 AMD GPU FSR4 选项暗中切换。
4. 每种 D3D11/D3D12/Vulkan 单独接入和报告，保留未知/不支持状态；初始化失败时不宣传 capability。
5. 对照自有 NGX 代理验证相同输入的输出与 history 行为；同一入口只由一套明确加载链接管，避免代理冲突。
6. 将补丁、构建方式、上游差异和许可义务写入维护说明；分发前核对实际组合的许可证，不凭 IPC 边界自行宣布豁免。

输出 ADR 决定继续维护 OptiScaler fork、向上游贡献或保留定向代理。不能仅因覆盖 API 多就放弃已验证的最小路线。

### M9.C D3D12 资源与命令提交

最大风险是 Evaluate 得到的 command list 尚未提交。禁止在回调里等待该未提交工作对应 fence，也不能擅自 close/execute 游戏拥有的 command list。

1. 独立 harness 复现“记录输入生成 → Evaluate → 后续命令 → 提交”的真实顺序，画出 producer/consumer 时间线。
2. 比较可行的提交拦截、队列边界或互操作设计；先用 ADR 固定方案与引擎侧前提，再写完整 backend。
3. 显式记录资源 state、队列归属、fence、descriptor、heap 与生命周期；跨队列等待与 device lost 单独处理。
4. 输入何时可读、输出何时可写、游戏何时能消费都必须有可验证同步；不能只依赖 `Sleep` 或 CPU mutex。
5. 验证多 command list、多帧 in flight、resize、feature release、游戏退出和超时，不泄漏 fence/heap。
6. 在实际 Proton/vkd3d/FEX 链路重复验证；Windows 原生 GPU 样例通过只能作 `host_test`。

### M9.D Vulkan 输入边界

先区分 Windows 游戏经 Proton 的 Vulkan NGX、原生 Linux Vulkan 和仅 present layer；它们的 ABI、句柄归属和部署方式不同。

1. 在真实 SR Evaluate/dispatch 边界获取引擎时序资源，明确 `VkDevice`、queue、image/buffer 与 command buffer 所有权。
2. 独立验证 layout transition、access/stage mask、queue family ownership 与 semaphore/fence；不能把 opaque VkImage 直接发给跨进程 daemon。
3. 新建资源桥时先使用可审计复制路径，再评估 external memory 与同步扩展；可导出 FD 不等于端到端可共享。
4. 对原生 AArch64、x86 guest layer 与 host thunk 分开构建/装载验证，不共用错误架构的 ELF layer。
5. 继续走相同 `session/context/frame/history_generation` 合同，验证多 swapchain/多 viewport 时不串 history。

### M9.E 原生 FSR 输入专项入口（仅规划）

用户的拓展问题原则上可行：在游戏 FSR 调用边界取得输入后转给同一 NPU 服务，不必先伪装成 DLSS。当前只准备后续研究任务，不承诺通用 DLL 替换。

专项第一份产物应是一页入口调查：真实 SDK/API 版本、动态 DLL 还是静态/引擎集成、公共导出、context/dispatch/query/configure/destroy 生命周期、SR 与其它 effect 的区分。

动态 API 路线需核对 descriptor/pNext/版本/错误码/资源状态，静态链接可能需要引擎或特定游戏适配。仅有 FSR1 色彩输入无法补出完整 FSR4 时序数据。

调查通过后再单列 FSR 专项路线和验收，复用 M3–M6 方法。首批不要同时升级 v07 模型和换 FSR 输入层，也不要以更改一个文件名宣称兼容新 FSR SDK。

## 6. 配置与接口约束

profile 的能力声明只包含证实的功能，例如固定 SDR shape、支持的 MV 格式和 reset 语义；协议握手据此拒绝未知组合。

每个新增 frontend 都实现统一的 create/evaluate/reset/destroy 生命周期，并把 API 特定资源转换保留在 adapter；daemon 不理解任意游戏指针。

资源句柄与前端 API 对象不能序列化成整数后直接跨进程解引用。跨边界只发送协议约定的数据或经独立验证的共享资源引用。

运行时可以按能力选择已验证后端，但不能将未知 API 映射到“最接近”的实现。fallback 必须满足当前帧、目标尺寸和同步合同，并在遥测中明确记录。

## 7. 失败与回归矩阵

| 失败 | 定位方式 | 必须处理 |
| --- | --- | --- |
| 游戏升级后 DLSS 选项消失 | 导出/查询/加载链与 build hash | 旧变体失配，重新跑 M3 |
| DLL 载入但没有 Evaluate | feature/API 探针 | 不判支持，找真实输入边界 |
| D3D12 卡在 fence | command list 提交时间线 | 回退方案，禁止无限等待 |
| Vulkan 旧帧/花屏 | layout/ownership/帧身份 | 停用该 bridge，回复制样例 |
| OptiScaler 接入输出有误 | 同输入与定向代理对照 | 检查规范化语义，不先改模型 |
| 新驱动/Proton regression | 锁定旧环境 A/B | 限定变体并保留已验证版本 |
| 多视口串 history | context/reset trace | 修复隔离，回 M5 重验 |
| 含反作弊或禁止修改场景 | 已知加载约束与用户使用场景 | 记录不支持，不研究绕过 |

## 8. 验收门槛

- `source_review`：每个工作包有固定依赖 SHA、输入映射、资源时序、许可和部署冲突说明。
- `build` / `host_test`：最小样例和错误注入通过；源码存在或编译成功不等于游戏支持。
- `device_test`：实际 ABI/驱动/互操作链通过，真实 HTP 执行与输出可核对。
- `game_test`：每个变体重跑 M3–M6 必需项和 M7 恢复，记录 HDR/DRS 等未覆盖项。
- 所有 gate 使用 `not_run` / `pass` / `fail` / `blocked`；兼容性标签必须链接到具体组合报告。
- 没有覆盖矩阵证据不得发布“所有 DLSS/FSR 游戏可用”；原生 FSR 入口调查完成也不等于 FSR backend 完成。

## 9. 交接与 AI 提示词

交接包含变体矩阵、固定源码、adapter 输入映射、同步时间线、最小失败复现、游戏测试清单、性能结果与恢复步骤。报告保存到 `docs/validation/M9/YYYY-MM-DD-<work-package>.md`，交接为同名 `-handoff.md`。每次只选择一个工作包，按结果更新状态与 [ADR](../templates/adr.md)。

```text
实施 M9 的一个明确工作包，不同时扩展模型与多个 API。先读取公共合同、
M3–M7 已有证据及本路线，列出准确游戏/API/ABI/Proton/驱动/模型组合。
OptiScaler 需要新增后端，现有 GPU FSR4 选项不是 NPU；D3D12 不能等待
尚未提交的游戏 command list，也不能擅自 close/submit 它；Vulkan 必须证明
layout、ownership 和同步，不能跨进程直接传 VkImage 指针当共享资源。
每个变体重跑正确性、时序、性能和恢复验证。无设备只做源码/构建/host_test。
原生 FSR 本轮只产入口调查与独立工作包，不提前实现或声称支持全部 FSR 游戏。
输出具体修改、最小复现、证据链接、gate 状态和下一步，不编造兼容性。
```
