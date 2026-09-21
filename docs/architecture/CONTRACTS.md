# 跨模块合同草案

状态：**draft-0，设计提案，不是已实现、已冻结的 ABI 或协议**。本文件是各节点共享语义的起点。字段样例不代表设备信息、模型生成结果或实测数据；实施时先定义 schema 和测试，再由一次配套变更固定版本。

[实施指南](../ai/IMPLEMENTATION_GUIDE.md) · [节点路线](../roadmap/README.md) · [状态页](../STATUS.md)

## 1. 模块边界

| 拟议目录 | 所有者与职责 | 不应越过的边界 |
| --- | --- | --- |
| `tools/device/` | M0：只读环境采集、来源与缺项 | 不负责刷机、改内核或设置游戏 |
| `tools/qnn-probe/`、`runtime/qnn/` | M1：provider、backend/device/context/graph、真实执行与释放 | 不声称已处理完整游戏帧 |
| `tools/model/`、`runtime/gpu/` | M2：模型清单、量化、特征和后处理 | 不靠模型文件名推断布局或支持 |
| `adapters/ngx/` | M3：游戏 ABI、API、输入语义与纹理写回 | 不在 PE 进程中加载不匹配的宿主 QNN 库 |
| `protocol/`、`runtime/core/` | M4：序列化、会话、帧生命周期、调度、错误 | 不直接复用 XLSR 单 RGB 协议承载时序模型 |
| `tests/`、`tools/replay/` | M5：序列参考、历史/重置与故障恢复 | 不把 mock/合成图结果外推为游戏画质 |
| `tools/bench/` | M6：阶段时间、帧年龄、延迟、功耗 | 不把 NPU execute 时间当整帧时间 |
| `launcher/`、`packaging/`、`profiles/` | M7：配置解析、启动、事务部署与恢复 | 不覆盖非本项目拥有的配置或资产 |
| `decky/` | M8：控制客户端与可视状态 | 不承担逐帧图像传输，不复制一套安装逻辑 |
| `adapters/optiscaler/` 等 | M9：扩展输入/API | 不绕开 M4–M6 的正确性和性能门槛 |

目录在需要实现时创建。这里的分工不要求一个源文件只能由一个节点修改，但公共接口变动必须同步生产者与消费者。

## 2. 统一标识与版本

| 字段 | 语义 |
| --- | --- |
| `schema_version` | JSON 文件/控制消息的结构版本，不能与模型版本或帧协议版本混用 |
| `protocol_version` | 帧协议兼容版本；不兼容时握手失败，不能猜测 payload |
| `run_id` | 一次验证或性能运行的唯一标识 |
| `device_profile_id` | 一份设备/镜像/运行栈记录的标识，不能只用“Odin3” |
| `model_manifest_id` | 模型、context、量化、shader 与目标元数据的一组锁定记录 |
| `service_instance_id` | 服务每次启动产生的新标识，区分重启前后的状态与计数 |
| `session_id` | 一个已认证连接/游戏会话的标识 |
| `context_id` | 一次超分 context 生命周期，隔离不同视口或不同创建实例 |
| `frame_id` | context 内单调递增的请求序号，不因历史重置复用 |
| `history_generation` | 历史重置时递增的代号；旧代输出不能写入新代 |
| `request_id` | 控制请求与回复的关联标识，不能拿当前 UI 游戏状态猜测归属 |

控制 JSON 中，可能超过 JavaScript 安全整数范围的 ID/计数使用十进制字符串或明确的字符串 ID。二进制协议的整数宽度与端序由 M4 schema 固定。不要直接序列化编译器 C/C++ struct，不依赖本地指针宽度、padding 或字节序。

schema 升级要说明兼容策略：新增可选字段能否被旧端忽略；必需语义变化则升级版本并显式拒绝。禁止单凭消息长度猜版本。哈希使用明确标记的算法，例如 SHA-256；若使用内容寻址 ID，先定义规范化输入，不能对不同 JSON 空白格式作不稳定比较。

## 3. 设备记录与模型清单

M0 的设备记录至少包括：记录时间与采集方法、设备树 model/compatible、SoC 标识及来源、系统镜像/内核/glibc、GPU 驱动与 API、Steam/Proton/FEX/DXVK/vkd3d 的版本与架构、CDSP/FastRPC 可观察状态、权限、工具缺项。未知项为 `null`，并注明原因。公共报告隐藏不必要的序列号、用户名和主目录。

M2 模型清单至少包括：源 SDK/模型版本与许可来源、脚本提交、权重/context/shader 哈希、QAIRT 工具与 runtime 版本、SoC/HTP 目标、graph 名、输入输出 tensor 的名称/形状/布局/类型/量化、分辨率档、参考数据集与验证报告。

```json
{
  "schema_version": "draft-0",
  "example_only": true,
  "model_manifest_id": "example-fsr4-v07-540-to-1080",
  "algorithm": "fsr4-v07-research-port",
  "target": {"soc_model": null, "htp_arch": 79, "device_verified": false},
  "toolchain": {"qairt_version": null, "converter_commit": null},
  "render_size": [960, 540],
  "display_size": [1920, 1080],
  "graph": {
    "name": null,
    "inputs": [{"shape": [1, 540, 960, 16], "layout": "NHWC", "dtype": "int8", "quantization": null}],
    "outputs": [{"shape": [1, 1080, 1920, 8], "layout": "NHWC", "dtype": "int8", "quantization": null}]
  },
  "artifacts": [],
  "validation_gate": "not_run"
}
```

这是不完整说明性样例，生产加载器应拒绝缺少 graph 名、量化、哈希和实际资产的 manifest。实际 context 可能有 dummy output，必须从元数据枚举并记录，不能只按上述示例分配输出数组。

图 tensor 的量化定义需显式记录 convention。QNN 的 scale/offset 不能不经转换就当成其它框架的 zero-point；具体类型按所锁定 SDK 头文件解析，并用已知数值测试。型号/架构预测值与设备确认值必须分字段记录。

## 4. 规范帧输入

适配器负责将游戏语义映射为明确的内部表示；服务不通过纹理名称猜格式。支持能力先通过握手确定。

| 类别 | 最低语义 |
| --- | --- |
| 图像 | 渲染/显示尺寸、有效子区域、颜色格式、线性/sRGB/HDR、pre-exposure、row pitch、数据长度 |
| 运动 | 网格尺寸、XY 通道格式、数值单位、方向、Y 轴、scale、是否包含 jitter |
| 相机/时序 | 当前 jitter、是否 reset、history_generation；需要时记录相机/深度约定 |
| 深度与 masks | 是否提供、格式/范围/反转约定、实际是否使用；缺失时的明确能力限制 |
| 输出 | 游戏期望尺寸/格式、可写容量、资源状态与所有权；不是任意 RGB 文件 |

内部像素空间的原点、运动向量“当前到上一帧”或相反方向、jitter 单位由 M3/M5 通过平移样例确定并写入 schema。草案不强制假定所有游戏使用同一方向。适配器映射后服务只接受一种已经说明的规范形式，避免多处隐式乘尺寸、翻 Y 或二次减 jitter。

输入和输出的颜色精度是能力合同。RGBA8 复制基线不宣称完整 HDR；不支持的格式、动态分辨率和多视口明确拒绝。不能把原图 memcpy 到不同尺寸/格式的输出资源作为成功回退。

## 5. 会话、历史与资源生命周期

拟议状态流程：

```text
connect → negotiate → create_context → ready
ready → validate_frame → capture_complete → execute → reconstruct → return_result → pending_consumption
pending_consumption → result_consumed(success) → commit_history → ready
pending_consumption → result_consumed(failure)/timeout/disconnect → invalidate_history
reset/change_profile/discontinuity → invalidate_history → new_generation → ready
error/disconnect → quarantine_or_cleanup → destroy_context → closed
```

- M4 基线每个 context 同时最多一个在途请求，M4 最小实现允许只支持一个会话/一个 context；第二个明确拒绝，比共享历史安全。
- 多会话支持时，history、recurrent buffers、profile、帧号与资源池必须分别归属，不共用全局“上一帧”。
- 发起 reset 后旧代在途结果不得覆盖新代。需要等完成或隔离资源，不能仅清计数。
- 正常输出应匹配完整的 `(service_instance_id, session_id, context_id, frame_id, history_generation, model_manifest_id)`。
- 适配器通过带完整帧身份的 `result_consumed` 成功/失败通知确认写回；成功指按图形 API 的同步和资源语义可供后续游戏命令消费，不表示已经物理显示。服务收到并校验成功通知前保持 pending，不执行下一帧；通知重复处理必须幂等，丢失/超时/失败则失效历史。socket send 成功不等于写回成功。
- 去重终态元数据必须有界，不能靠无限保存实现幂等。当前 host 合成基线分别 FIFO 保留最近 4 个消费决定和 4 个 reset 结果；首次终结决定进入窗口，重试或冲突不刷新顺序。窗口内同参重试幂等、冲突拒绝；窗口外通知以不可重试的 unknown/expired 语义拒绝，不能再次提交/失效 history、释放其它资源或推进 generation。正式 M4 协议需版本化或协商保留窗口和稳定错误，不得默认为无限重试。
- 记录处理完成与游戏实际写回两个事件。history/recurrent 优先采用 current/next 双缓冲：完成全部必要处理并确认消费后交换；若沿用 in-place 更新，任何部分更新失败或消费不确定均使整套历史失效，等待在途工作结束后重新初始化。仅跳过一个 commit 标记不能撤销 GPU 已写入的数据。
- GPU readback 完成前 CPU 不能读；NPU 完成前 GPU 后处理不能读；游戏继续使用输出前写回必须可见。D3D12 未提交命令的 fence 不能在阻碍提交的回调中等待。
- 超时代表调用方等待预算耗尽，不代表 graphExecute 已取消。仍在使用的 context/buffer/library 不能释放或重用；先停止新请求，隔离旧工作，再按后端能力退出/恢复。
- 断连、device loss、服务重启、休眠恢复均产生可观察事件。自动 DSP reset 不属于默认恢复动作。

`draft-0` 建议由原生 context 所有者作为 generation 的唯一权威：M2 离线时是执行器，M4 接入时是 daemon。创建回复给出初始 generation；适配器显式 reset 时发送带当前 generation 和 `request_id` 的请求，服务等待或隔离旧工作、失效/初始化历史后递增并回复新 generation，适配器随后才发送该代帧。`request_id` 在一个 context 生命周期内必须唯一且不可复用；有限窗口淘汰后，服务无法永久区分 opaque ID 的历史复用与新请求。保留窗口内的重复 reset 返回同一结果，不重复递增；窗口外带旧 generation 的重复请求拒绝并要求重新同步。帧中的 reset 来源仅作记录，不再触发第二次递增。服务检测到连续性丢失时拒绝继续并要求重新握手/reset，不能单方换代后默默接受旧代输入。M4-A 实施前用 ADR 冻结此流程或替代流程，并同步 M2/M5 与协议测试。

队列深度、缓存帧或多帧异步模式只能在后续独立模式中加入；不能改变同帧基线的含义。每种模式有独立的质量/延迟报告和默认启用条件。

## 6. 传输、边界检查与时钟

首个跨 PE/宿主桥接采用本地 TCP 复制基线，控制面可用同用户 Unix socket。具体 wire 字节布局、鉴权建立方式、错误回复和版本握手由 M4 小工作包配套实现。本文不声称 Linux FD 可直接穿过 WinSock。

必需校验：版本、完整读写、尺寸/stride/长度相容、整数溢出、允许格式、tensor 数量与上限、最大报文、会话所有权、重复或过期帧、超时、半包/断连。先校验再分配；按照已声明上限分块读，不因包头声称的长度分配任意内存。

每个连接有会话凭证与明确本地可访问范围；凭证不放入公开日志。之后的 memfd/DMA-BUF 方案需要独立的句柄生命周期、权限与 cache 同步合同，不能把 fd 数值当跨进程共享资源。

跨进程时间不默认同源。记录 `clock_domain`、单调时间单位和采集点；截止预算使用可明确解释的相对期限或已校准时钟。GPU timestamp、QNN profiling、宿主 monotonic 与外部输入到显示测量分别记录，不直接相减得到虚假延迟。

## 7. 状态与计数

配置中的 `enabled` 表示希望启用，`active` 需要实际接入和运行证据。模型可加载、客户端已连、HTP 曾执行与游戏当前采用输出是不同状态。

状态至少提供：schema、服务实例、采样时间、profile/AppID、实际 backend、模型清单、连接/context 状态、最后错误、回退原因和数据新鲜度。UI 不能只显示 cached 的上次成功而隐藏服务离线。

建议分别累计：

- `evaluate_requests`：游戏请求数。
- `htp_execute_successes`：实际 HTP 执行成功数，不计 mock/CPU。
- `fresh_results`：完整生成的新结果数。
- `output_writebacks`：经适配器确认写回数。
- `cached_redisplays`、`fallback_frames`、`rejected_frames`、`timeouts`：独立故障/降级计数。

计数不能简单相等推定正确性，应以帧追踪核对；同一次重试、返回缓存、输出丢失都会改变关系。吞吐同时报告游戏 present 与实际新输出，避免重复帧把 FPS 虚增。

错误至少包含稳定类别、阶段、SDK/系统原始代码、是否可重试与建议恢复动作。建议类别：`SETUP`、`ABI`、`FIRMWARE`、`ACCESS`、`MODEL`、`TRANSPORT`、`GPU_SYNC`、`OUTPUT`、`QUALITY`、`PERF`。原始错误码不可被泛化“初始化失败”吞掉；错误枚举首次实现时再冻结数值。

## 8. 游戏配置与安装事务

游戏 profile 绑定 AppID（或明确的非 Steam 标识）、可执行文件/构建哈希、API/PE ABI、Proton/FEX 栈、模型档、输入语义修正、冲突列表与验证报告。示例档不能进入默认白名单。

配置优先级建议：显式本次 CLI 参数 → 已验证的每游戏设置 → 用户全局偏好 → 保守内置默认。解析后保存“实际生效值 + 来源”，不只记录原始配置。禁用为默认；全局偏好不能越过 capability 检查。

部署按计划、预检、备份、写入、校验、提交与回滚分阶段记录。每个路径先确认归属，记录原始和安装后哈希。恢复时，原来不存在的文件只删除本项目创建且仍与记录匹配的版本；原来存在的文件校验备份后原子恢复原内容和权限。用户或游戏更新后的文件保留并报告冲突，备份损坏也不得强制覆盖。模型/运行库集中缓存不能导致所有游戏被一次升级同时破坏，应按 profile 锁定版本。

启动器处理原命令的 argv，不使用字符串 eval；正确转发信号和退出码。Steam 参数采取追加/合并/恢复策略，不清空 Armada Control 或其它兼容工具的设置。UI 通过 M7 的同一控制入口操作，不自建一套文件修改逻辑。

## 9. 证据与合同变更

证据类别与检查结果按[实施指南](../ai/IMPLEMENTATION_GUIDE.md)统一。原始数据与公开结论分开，保留 run/commit/model/device 标识。

共享合同变更的交付清单：

1. ADR 写明触发原因、备选、兼容/迁移/回滚策略。
2. 更新 schema/协议版本和本文件，注明仍是 draft 还是已实现版本。
3. 同步所有生产者/消费者及样例，覆盖旧版本拒绝或迁移测试。
4. 更新相关节点的交接和状态记录，不在未验证平台声明兼容。

各节点指南与本文件冲突时先核对最近的实现和 ADR，形成明确决定后一起修改；不能选择最方便的一份文字作为绕过验收的依据。历史研究中的 ABI 和性能描述保留其来源，不自动升级为本项目合同。
