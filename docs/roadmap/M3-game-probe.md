# M3 · 游戏接口探针与输出回写

状态：**`not_started`；真实设备与游戏 gate 均 `not_run`。** 实施只从 [D19–D22](DEVICE_EXECUTION.md#m3真实游戏接口与回写) 选择一个小批次；D19 需要目标设备兼容栈，D20–D22 还需要用户选定的游戏。无设备的自有 PE/D3D11 fixture 属于 [E 队列](HOST_PREPARATION.md#e协议与主机工程准备)。本文把“游戏有 DLSS 菜单”转化为可审计的 NGX 调用、资源语义和输出回写证据，技术正文不作为第二套队列。

- 前置依赖：M0 的设备档案、可正常运行的原游戏、明确的游戏进程和兼容栈。
- 可并行：M1/M2。此节点不需要 NPU，也不能证明 NPU 或 FSR4 已运行。
- 交付：一个限定游戏/API/ABI 的可恢复探针、输入语义档案、回写测试与 `docs/validation/M3/YYYY-MM-DD-<work-package>.md`。
- 状态依据：[D 执行队列](DEVICE_EXECUTION.md)、[项目状态](../STATUS.md)和[跨组件合同](../architecture/CONTRACTS.md)。协议名以 `draft-0` 为准，尚未冻结 ABI。

## 1. 目标与范围

实现首个 D3D11 NGX Super Resolution 接入，从加载、能力查询、Create、Evaluate 到 Release/Shutdown 全程可观测。先用自有测试宿主验证导出和 ABI，再在实际游戏中证明读取与写回的是引擎传入的正确纹理。

本节点不实现 QNN、FSR4 网络、全局 GPU 仿真、DLSS 帧生成、Ray Reconstruction、Reflex、OptiScaler 后端或 ReShade add-on。D3D12/Vulkan 只记录实际调用并明确返回不支持，不因导出函数存在就宣称已支持。

首游戏选择条件：用户拥有、允许修改的离线场景、在当前 Armada 栈稳定运行、有可重复测试场景，并能实测触发受支持 API 的 DLSS SR Evaluate。不能预先把 Rise of the Tomb Raider、某个 AppID 或 D3D11 DLSS 可用性写成已确认事实。

## 2. 必读源码与需要回答的问题

以下固定快照支持现有研究结论。实现前核对本地 SHA；更新上游必须单独记录差异，不能同时悄悄扩大范围。

| 固定来源 | 阅读重点 |
| --- | --- |
| [full_proxy.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/full_proxy.c) | 导出、参数表 ABI、OptimalSettings、D3D11 Create/Evaluate、纹理格式、回写与 D3D12 stub |
| [REPRODUCING.md](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/docs/REPRODUCING.md) | DX12 开关与 Quality 档说明，需要和实际 API/尺寸对照 |
| [d3d12_inject.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/injector/d3d12_inject.c) | 游戏专用注册表注入逻辑；名称不代表 D3D12 渲染后端 |
| [proxy/build.sh](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/build.sh) | 原 x86-64 PE 产物、链接与导出方式 |
| [fsr4cap.ini](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/fsr4cap.ini) | 模式默认值及静默双线性回退风险 |
| [原研究留档](../reference/2026-09-20-feasibility.zh-CN.md) | 项目边界、已有证据、平台与 DLL 加载链 |

必须生成一张“文档宣称 / 源码行为 / 实测结果”对照表。上游 D3D12 Create/Evaluate 返回不支持，而复现文档要求开启 DX12；两者的矛盾尚未解决。不可自行判定作者实验不存在，也不可照抄成通用 D3D12 支持。

同样，菜单 Quality 不等于固定 960×540。记录 OptimalSettings 请求和响应、Create 尺寸、Evaluate 实际资源尺寸及有效区域，任何不一致都先标记为失败或待解释。

## 3. 输入与拟议目录

输入包括 M0 的 `device_profile_id`、游戏版本/AppID、可执行文件哈希、Steam/Proton/Wine/FEX/DXVK 版本、进程位数、既有 mod 清单，以及未经修改的启动基线。缺失字段写 `null` 并说明如何收集，不能猜测。

```text
adapters/ngx/abi/             # 已核对的导出、调用约定、参数访问边界
adapters/ngx/d3d11/           # 资源描述、读取、确定性测试回写
adapters/ngx/probe/           # 有界日志、捕获、测试模式
adapters/ngx/lifecycle/       # 初始化、feature handle、销毁和状态机
profiles/                    # 候选与已验证游戏档案，状态必须分开
tests/ngx/                   # 自有最小宿主、导出检查与生命周期测试
tests/fixtures/              # 可公开的合成纹理和元数据
docs/validation/M3/          # 日期-工作包报告及同名 -handoff.md
```

这些目录是拟议职责，不要求一次建立所有空目录。按小 PR 创建实际需要的代码。

游戏侧产物为与实际游戏/兼容栈匹配的 Windows PE DLL，通常需要验证 x86-64 PE，不能因为宿主是 ARM64 就统一编译为 AArch64 DLL。原生运行时将是 AArch64 Linux ELF；两者不直接互相链接，也不共享 C++ 指针或 COM 句柄。

## 4. 可审查的小 PR 顺序

### PR M3-A：探针宿主与 ABI 最小面

1. 建立只包含必要导出的适配器和自有测试宿主；记录工具链、目标三元组、位数、导出列表。
2. 检查返回类型、调用约定、参数表 vtable 顺序、handle 所有权；从固定来源获得定义并保留来源/许可证说明。
3. 在宿主中覆盖 Init → GetParameters → GetCapability → Create → Evaluate → Release → Shutdown。
4. 不支持的功能明确返回相应错误；禁止为“让菜单出现”把所有能力和错误都改成成功。
5. 验证 DLL 加载与卸载不会访问不存在的游戏路径；`DllMain` 中不做网络、GPU 初始化或阻塞等待。

完成条件：可重复构建且导出检查通过。宿主测试是 `host_test`；它不能把游戏兼容 gate 设为 `pass`。

### PR M3-B：实际加载链与最小能力曝光

1. 只对选定游戏做临时部署，记录计划修改的文件、哈希、原始启动参数和恢复路径。
2. 观察游戏加载的是 NGX application API、feature DLL、Streamline 还是其它路径，再决定代理 DLL 名称。
3. 分开验证 `nvngx.dll`、`nvngx_dlss.dll`、`dxgi.dll` 的职责；不把三者当成可互换入口。
4. 仅在证据需要时增加最小 NVAPI/DXGI 能力适配；保存改变前后的查询结果和游戏实际行为。
5. 不同时装入争夺同一入口的 OptiScaler 和自写 NGX 代理。恢复原配置后验证游戏能正常启动。

完成条件：日志证明当前游戏进程加载了指定哈希和 ABI 的代理，并捕获真实 Create/Evaluate，而非只有 DLL 载入消息。

### PR M3-C：资源观察与语义归一化

1. 在 Evaluate 读取颜色、MV、输出以及存在的 depth、exposure、pre-exposure、jitter、MV scale、reset 参数。
2. 记录资源类型、格式、尺寸、mip、array slice、采样数、usage、绑定标志和有效子区域；不隐式选第一个子资源。
3. 支持范围从单采样 2D 纹理开始；对未实现 MSAA、数组、特殊视图或格式返回明确诊断。
4. 保留“参数不存在”“值为零”“未消费”三种状态；不能将缺失 jitter/reset/exposure 统一写成有效的零或一。
5. 用合成平移、棋盘格、不同通道色块验证 MV 方向、像素/归一化单位、Y 轴、颜色顺序和 row pitch。
6. 写入候选 profile 的映射证据；全量帧捕获默认关闭，只在有界帧数和磁盘配额内手动启用。

完成条件：每个必需字段都有来源与转换说明；未验证语义仍标为未知，不通过填默认值掩盖。

### PR M3-D：同帧确定性回写

1. 先使用测试宿主创建已知输入和输出纹理，写入有明确帧标记的合成图案，再读回校验。
2. 在游戏中提供明确命名的 `probe-spatial` 测试模式，将当前帧按已验证格式上采样到正确输出尺寸。
3. 只在 debug 捕获中加入帧标记；正常模式不污染画面。记录输入帧与输出回写的对应关系。
4. D3D11 即时上下文路径先验证 Copy/Map/Unmap/Update 的调用合法性；遇 deferred context 先拒绝，另做设计。
5. 保存和恢复适配器实际改动的 GPU 绑定状态；不能假定游戏下一阶段会重新绑定全部状态。
6. 明确此模式没有运行 FSR4/NPU；不要给它标记 `npu_active=true`。

完成条件：测试宿主能验证输出内容，实际游戏能确认同一 Evaluate 输出纹理被正确消费；仅截图“画面正常”不足以通过。

### PR M3-E：生命周期、故障与报告

测试重复 Create/Release、无效 handle、重复 Shutdown、窗口切换、菜单换档与设备丢失。按 API 合同处理错误，所有资源与线程有退出路径，日志限速不阻塞每帧。

将暂不支持的 D3D12/Vulkan 调用、未知格式、未知 ABI 和模式变化整理为机器可读错误及面向人的解释。未选中可用游戏时，保留宿主产物，将游戏 gate 标为 `blocked` 并写清缺失输入。

## 5. 拟议接口与数据例子

以下是语义草案，不是已发布 JSON schema 或 wire ABI；最终字段约束以[合同](../architecture/CONTRACTS.md)为准。

```json
{
  "schema_version": "draft-0", "example_only": true,
  "device_profile_id": "odin3-armada-unverified",
  "model_manifest_id": null, "service_instance_id": null,
  "game": {"appid": null, "build_id": null, "exe_sha256": null},
  "adapter": {"api": "d3d11", "pe_machine": null, "mode": "probe-spatial"},
  "session_id": "example-session", "context_id": "example-context",
  "frame_id": "17", "history_generation": "0",
  "render_size": [960, 540], "display_size": [1920, 1080],
  "mv": {"direction": "unverified", "units": "unverified", "scale": [1, 1]},
  "reset": {"present": false, "value": null},
  "depth": {"present": false, "consumed": false},
  "evidence_level": "host_test", "gate": "not_run"
}
```

尺寸仅示意，不能据此生成已验证 profile。实际 `pe_machine`、模式和能力只有采集后才能填写确定值。`model_manifest_id` 在未接模型时应为 `null`，不能填入任意 FSR4 名称暗示模型已运行。

内部接口可拆为 `inspect_inputs`、`normalize_metadata`、`capture_current_frame`、`write_probe_output`、`release_context`，返回结果必须区分缺少参数、格式不支持、GPU 失败与生命周期错误。

## 6. 所有权与失效规则

| 对象 | 所有者与规则 |
| --- | --- |
| 游戏输入/输出资源 | 游戏所有；适配器只在约定回调期间访问；跨回调保留须正确 AddRef/Release |
| 参数表与 feature handle | 严格按 NGX 版本与导出语义；适配器自建对象有类型/代际检查 |
| staging/临时纹理 | 适配器 context 所有；尺寸或设备改变后销毁重建，不能跨设备复用 |
| 映射内存 | Map 成功到 Unmap 之间有效；按 RowPitch 逐行处理，不把 Map 指针放入异步队列 |
| 捕获文件/日志 | 探针会话所有；有帧数/字节上限；不写令牌、用户目录或未脱敏路径到公开报告 |

首版可明确只允许一个活动 feature；第二个返回受控的“不支持”。若游戏需要多 feature，则实现独立 context 或换候选，不能共享同一组全局输入/输出状态。

在 Create 前发现缺少能力就拒绝创建；Create 后故障只使用已验证的同帧测试路径或返回错误。不得重显旧帧并记成新成功，也不得将低分辨率输入直接当成高分辨率输出。

## 7. 测试矩阵与验收

| 层级 | 必测内容 | 可证明的范围 |
| --- | --- | --- |
| `source_review` | 导出/ABI 来源、DX12/preset 矛盾表、生命周期审查 | 设计依据与风险识别 |
| `build` | 指定 PE 架构、导出符号、依赖、可重复构建 | 构建产物正确，不代表加载成功 |
| `host_test` | 参数缺失、格式/stride、合成平移、尺寸、重复创建释放 | 测试宿主下功能正确 |
| `device_test` | 目标兼容栈加载、资源操作与设备丢失 | Odin 3 当前软件组合行为 |
| `game_test` | 真实 Evaluate、实际纹理、菜单/尺寸、回写、恢复 | 单游戏/构建/API/profile 的兼容证据 |

- 每个 gate 使用 `not_run / pass / fail / blocked`，附证据路径；不能把构建成功自动升级成真机通过。
- M3 通过需要 `game_test` 证据，且 API、DLL ABI、必需输入语义和同帧回写已确认。
- DLSS 菜单、已加载 DLL、NVAPI 查询成功或空间上采样画面均不能独立代表 M3 全部通过。
- M3 不要求 NPU 性能；可记录额外开销，但禁止把探针 FPS 作为 FSR4 NPU 收益。
- 首次门槛不包含 HDR、DRS、D3D12、Vulkan；发现这些路径应拒绝或明确保持关闭。

## 8. 无硬件工作与交接

没有 Odin 3 时可完成 ABI 审查、PE 构建、模拟参数、合成纹理宿主、日志 schema、错误与卸载测试。不能宣称 Armada DLL 加载正确、游戏已有 DLSS SR 入口或真实资源能回写。

所选 D 批使用一份短记录，至少包含源 SHA/编译命令、产物哈希、ABI/API、游戏/profile gate、恢复说明、最小复现、失败样例和下一步。改变公共 API/作用域时才补 ADR，不再强制 validation + handoff 成套文件。

M4 的输入必须包含：输入/输出纹理格式与尺寸合同、MV/jitter/exposure/reset 已知与未知项、Create/Release 生命周期、已验证回写函数和游戏加载链。任何未知项都不能在 M4 中默默补常量。

## 9. 旧执行提示（停用）

> 下列历史提示不得再用于整体启动 M3；当前只从 [D19–D22](DEVICE_EXECUTION.md#m3真实游戏接口与回写) 选择一个叶子。保留它仅供核对技术禁区。

```text
请在本仓库实施 M3 游戏接口探针。先读 docs/STATUS.md、
docs/ai/IMPLEMENTATION_GUIDE.md、docs/architecture/CONTRACTS.md、
docs/roadmap/M3-game-probe.md 和引用的固定 SHA 源码，再检查当前代码与 Git 状态。
目标是 Odin 3 / Snapdragon 8 Elite / Armada OS；
实际系统、PE ABI、首个游戏与兼容栈以 M0 档案为准，未知就写未知。
只实现本次选定的一个小 PR：优先 ABI/宿主，其次真实加载探针，再做同帧回写。
只覆盖 D3D11 NGX SR；不引入 QNN，不做 D3D12/Vulkan/帧生成/通用 GPU 仿真。
用真实日志解决上游 DX12 文档与 D3D11 源码、Quality 与实际尺寸的矛盾；
不能用 DLL 名称、菜单项或推测代替证据。DLL 架构匹配游戏进程，host 为 AArch64 ELF。
保留颜色、MV、输出、jitter、reset、exposure/pre-exposure 和 depth 的存在性与语义，
未消费字段明确标注；对未知格式、子资源、deferred context 明确拒绝。
用合成输入证明 RowPitch、通道、MV 方向/尺度和输出写回；确保资源所有权与状态恢复。
不修改其它游戏或全局环境；任何临时部署保存哈希与恢复清单，结束后验证恢复。
使用 source_review/build/host_test/device_test/game_test 区分证据，
gate 使用 not_run/pass/fail/blocked。无硬件就完成可做项并保留 game gate 未通过。
完成后给出改动文件、构建与测试命令/结果、未解决问题和最小下一步，
更新验收报告与交接记录，不把测试模式或构建产物称为 FSR4/NPU 已支持。
```
