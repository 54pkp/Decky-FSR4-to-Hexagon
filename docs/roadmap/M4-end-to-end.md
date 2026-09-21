# M4 · 同帧端到端闭环

状态：**`not_started`；真实设备与游戏 gate 均 `not_run`。** 实施只从 [D23–D27](DEVICE_EXECUTION.md#m4跨进程同帧闭环) 选择一个小批次；均需要目标设备，其中 D25–D27 还需要游戏。无设备 codec/mock 按 [E 队列](HOST_PREPARATION.md#e协议与主机工程准备) 验收。本节点把 M3 的真实游戏输入接入 M2 的 FSR4 GPU/HTP 后端；技术正文不作为第二套队列。

- 前置依赖：M2 的真机模型/前后处理验证，以及 M3 的真实游戏接入与回写 gate 均通过。
- 无硬件时：可开发协议、模拟服务与故障注入；这不满足 M4 的真机/游戏验收。
- 首个基线：固定形状、SDR、一个会话、一个 context、单请求在途、同帧同步返回、CPU staging + loopback TCP。
- 交付：可观测的最小闭环、故障隔离、可复现脚本与 `docs/validation/M4/YYYY-MM-DD-<work-package>.md`。

[D 执行队列](DEVICE_EXECUTION.md) · [跨组件合同](../architecture/CONTRACTS.md) · [项目状态](../STATUS.md)。此处接口均为拟议 `draft-0` 语义，不是已冻结的 wire ABI；字段布局和错误码以合同及实现批次为准。

## 1. 目标、非目标与来源

目标是正确性与可解释失败；不以 FPS 提升作为本节点成功条件。复制基线可能很慢，但必须能定位时间花在游戏读回、传输、GPU 前处理、HTP、后处理还是回写。

本节点不加入共享内存、DMA-BUF、AHardwareBuffer、多帧流水、缓存帧重显、多游戏调度、动态分辨率、HDR 或 Decky UI。不得为了吞吐将 Evaluate(n) 的成功输出改成 n−k 帧。

| 固定来源 | 需要核对的内容 |
| --- | --- |
| [full_proxy.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/full_proxy.c) | D3D11 staging、TCP、输出转换与 UpdateSubresource；上游旧帧重显行为不可继承为基线 |
| [live_daemon.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/live_daemon.c) | 帧接收、时序处理、重连 invalidate、异步路径与固定尺寸假设 |
| [qnn_service.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/qnn_service.c) | 真正 graphExecute、GPU 同步、rpcmem、初始化/销毁、Android 专用内存路径 |
| [fsr4_service.h](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/fsr4_service.h) | 可参考函数边界；旧注释不能覆盖实际 `.c` 行为 |
| [fork qnn_runtime.cpp](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/daemon/src/qnn_runtime.cpp) | Linux QNN provider/context/graphExecute 工程参考；不能把 XLSR 张量当作 FSR4 |
| [D3D12 官方同步说明](https://learn.microsoft.com/en-us/windows/win32/direct3d12/executing-and-synchronizing-command-lists) | 扩展 API 前必须理解提交与 fence；本节点不将 D3D11 Map 方案直接搬过去 |

## 2. 输入交付与模块边界

开始前收齐 `device_profile_id`、`model_manifest_id`、M2 输出误差报告、QNN/HTP 实际后端证据、shader 哈希、固定形状、游戏/profile 与 DLL ABI、M3 资源语义和回写测试。缺一个实际依赖就保留相应 gate 为 `blocked`，不以模拟后端替代。

```text
protocol/                    # 控制/帧编解码、上限、版本协商、错误语义
adapters/ngx/d3d11/           # 当前帧读取、上传、游戏 API 返回语义
adapters/ngx/transport/       # PE/WinSock 客户端及超时、响应校验
runtime/core/                # AArch64 Linux 会话/context/帧状态与调度
runtime/qnn/                 # provider/context/graphExecute 和错误传播
runtime/gpu/                 # Linux GPU 前后处理与完成同步
tests/protocol/              # 分片/截断/畸形/版本/长度测试
tests/integration/           # 合成帧端到端、模拟服务与故障注入
tools/replay/                # 复用 M2 帧包，绕过游戏定位后端问题
docs/validation/M4/          # 日期-工作包报告及同名 -handoff.md
```

PE DLL 使用游戏实际 ABI；daemon 使用与 Armada libc/加载器匹配的 AArch64 Linux ELF。网络边界传序列化元数据和像素，不传指针、COM 对象、fd 整数或直接 memcpy 的 C/C++ 结构体。每个组件自行承担 ABI/对齐/大小端转换。

## 3. 逐帧顺序与必须保持的不变量

```text
Evaluate(frame n)
  → 校验 context、尺寸、格式、metadata 与可用后端
  → D3D11 当前帧复制到 staging；确认 GPU 完成；Map/逐行复制/Unmap
  → 发送 frame n；daemon 完整收包、鉴权、校验 generation 与容量
  → GPU 特征完成 → HTP graphExecute 完成 → GPU 重建/下一份历史准备完成
  → 返回 frame n 的有效像素与真实执行状态
  → 客户端检查 service instance/session/context/frame/generation/model/shape/length
  → 写回该 Evaluate 的输出纹理，满足 API 完成语义
  → 发送带完整帧身份的 result_consumed 成功通知
  → daemon 确认消费后提交历史；下一帧才能开始执行
  → 返回成功；接收下一次 Evaluate
```

基线没有 deferred-2 readback、跨帧 staging ring 或缓存帧回显。同一个 context 的 n+1 不得先于 n 完成有效写回确认和历史提交；未确认时保持 pending，不接收第二个并发帧，或给出明确 busy 错误。写回失败发送失败通知；通知丢失或连接中断则按超时策略失效。这里的消费按图形 API 语义判断，不等待物理显示。

输出 frame ID 相等只是必要条件，还需在测试宿主使用随帧变化的图案/输入摘要及输出校验，证明像素真的对应该输入。metadata 回显不能伪装像素来源证据。

## 4. 可审查的小 PR 顺序

### PR M4-A：协议编解码与受限模拟链路

1. 依合同实现握手、能力、CreateContext、Frame/Result、result_consumed 成功/失败通知、Reset/Destroy 和错误响应；先通过 ADR 冻结 generation 权威方及 reset 请求/回复语义。确认通知带完整帧身份，重复处理幂等；文档同步记录版本与变更。
2. 对长度、尺寸、乘法溢出、stride、数据类型、功能位和总内存做验证，分配前确认上限。
3. 正确处理 TCP 部分读写、合并报文、对端半关闭、截断与超时；不能认为一次 recv 就是一帧。
4. 只监听 loopback；每次启动使用会话凭证，避免其它本地进程误用；凭证不打印到日志或公开报告。
5. 模拟服务以确定性变换返回帧，携带 `backend=mock`；错误包和超时是可配置测试点。
6. 协议未知主版本/必需字段缺失时握手拒绝；不要按 payload 总字节数猜协议版本。

完成条件：模拟客户端与服务端在不同构建目标下互通，畸形输入被有界拒绝。结果只记 `host_test`。

### PR M4-B：原生单上下文执行器

1. 接入 M2 的模型 manifest 验证、QNN 初始化、固定 GPU 前后处理与连续帧执行。
2. CreateContext 前核对 context binary、graph 名称、输入输出数量、shape/layout/量化与 shader 集；不匹配立即拒绝。
3. 第一版支持一个活动会话与一个 temporal context；第二个明确拒绝，不复用旧会话的 history。
4. 图执行计数仅在实际 QNN 调用成功返回后增加；CPU/mock 后端采用不同值，禁止标成 HTP。
5. 每帧按实际格式/stride 复制；GPU/NPU 边界等待正确完成后再交接，先保留 M2 验证过的分配路径。
6. 不移植 Android AHB 快路径或扫描 `/proc/self/fd` 作为通用 Linux 方案；需要改变内存方式另立 ADR。

完成条件：M2 相同帧包经服务传输后，逐阶段和最终输出误差在事先记录的容差内；实际 HTP 证据与模型绑定。

### PR M4-C：D3D11 当前帧接入与真实回写

1. 复用 M3 已验证资源路径，将 metadata 与当前帧像素打包；Create 只暴露 manifest 支持的尺寸/模式。
2. 固定 SDR profile，输入转换按 M3/M2 合同执行；不丢失或重复处理 pre-exposure、jitter、MV scale。
3. 校验响应 service_instance/session/context/frame/generation/model 全部身份字段、期望尺寸/格式、payload 长度、后端与执行结果，然后再接触输出纹理。
4. 使用 M3 已验证的上传方式；输出纹理不是任意 RAM 缓冲，必须遵守 D3D11 usage/format/资源状态规则。
5. 禁止把低分辨率输入直接复制成高分辨率成功；只允许专门验证过的同帧空间回退模式。
6. 对 deferred context、D3D12 或未知 API 返回不支持。D3D12 需要单独解决队列/提交，不在回调中等待未提交的工作。

D3D11 readback 使用已提交工作的 event/query readiness 与有期限轮询；适用时使用 `D3D11_MAP_FLAG_DO_NOT_WAIT`，处理尚未就绪返回值，不在未知完成状态直接无期限阻塞 Map。超期停止该 context，保留在途资源至安全完成/隔离。驱动内部挂死无法由用户态超时保证取消，需记录 device lost 和进程/设备恢复边界。

完成条件：测试宿主可验证像素帧身份，真实游戏日志可串联 Evaluate → graphExecute → 输出回写；无旧帧替代。

### PR M4-D：故障隔离、断连与销毁

1. 覆盖启动前服务缺失、握手失败、模型不符、处理中断连、返回错误、上传失败和游戏直接退出。
2. 客户端等待必须有界；超时时丢弃本次响应资格，并停止继续使用该 context，不能接受稍后到达的旧响应。
3. QNN 同步调用未必可取消。网络超时不等于 HTP 工作停止；不得在另一线程并发 free context/rpcmem。
4. 对卡住的执行器隔离工作进程；按 SDK/驱动可保证的退出行为回收，无法安全回收时标记后端不健康并要求重建/重启。
5. 若计算已改变 history，但响应丢失、输出上传失败或消费通知缺失，context 下一次恢复前必须 reset/recreate，不假设历史和游戏仍连续。双缓冲在确认前不交换；in-place 路径失效全部历史，按 M2 规则恢复。
6. 服务重启产生新 `service_instance_id`；重连分配新的 session/context/generation，旧连接的异步完成和输出无条件失效；记录原因和恢复结果。

完成条件：应用可控制的 GPU readiness 轮询、网络等待和服务调度均有期限，故障注入无 use-after-free；不承诺强制取消挂死的驱动/SDK 调用。无法无缝恢复的情况明确要求重启该游戏/服务，记录实际恢复边界。

### PR M4-E：关联遥测与真机报告

日志可通过共同身份字段关联，并区分“请求收到”“HTP 执行完成”“后处理完成”“响应送达”“游戏输出回写成功”。计数不要求永远相等，但每个差值都要有失败/取消解释。

记录各阶段单调时钟时长、总回调阻塞时间、最大在途数、输入/输出帧差、已回退帧数与错误类别。GPU timestamp 与 CPU 时钟不直接相减；跨进程/跨时钟比较须说明校准方法。

## 5. 拟议结果语义与数据样例

```json
{
  "schema_version": "draft-0", "protocol_version": "draft-0", "example_only": true,
  "device_profile_id": "example-device",
  "model_manifest_id": "example-fsr4-v07-v79-manifest",
  "service_instance_id": "service-example-1", "session_id": "s-1", "context_id": "c-1",
  "frame_id": "42", "history_generation": "3",
  "backend": "qnn_htp", "result_kind": "fresh_npu",
  "input_frame_id": "42", "output_frame_id": "42",
  "fallback_reason": null,
  "timing_ms": {"readback": null, "ipc": null, "graph_execute": null, "upload": null},
  "evidence_level": "game_test", "gate": "not_run"
}
```

以上全部是示例占位，`qnn_htp` 只能由实际后端证据填入，`null` 表示未测量。实际 schema、错误码和整数范围见合同。状态至少区分 `fresh_npu`、显式空间回退和失败；不允许让 `mock` 伪装 `fresh_npu`。

内部执行接口建议保持 `create(validated_manifest)`、`execute(frame)`、`invalidate(reason)`、`destroy()` 四类职责。执行返回不仅有图像，还应有消费的 frame/generation、真实后端、成功阶段和可恢复性；不要只返回一个布尔值。

## 6. 所有权、同步与资源清理

| 资源 | 生命周期与规则 |
| --- | --- |
| D3D11 游戏资源 | 游戏所有；Evaluate 内按已验证方式使用，跨调用引用须显式保留；不得提前释放 |
| 客户端 staging/像素副本 | 适配器 context 所有；发送完成不等于响应成功；收到并校验响应前不覆写相关状态 |
| daemon 帧缓冲 | 完整验证后分配；GPU/NPU 持有期间不能复用或释放 |
| QNN tensor/rpcmem | 执行器所有；直到 graphExecute 和后续消费者完成；按正确次序解除注册再释放 |
| GPU history/recurrent | temporal context 所有；任何会话切换与不连续处理须失效，不能跨用户或游戏复用 |
| socket 与凭证 | 当前会话所有；断连关闭并销毁资格；不把 TCP 连接地址当作足够的身份验证 |

析构顺序必须有测试：停止接收新请求 → 令在途请求完成或进入受控隔离 → 结束 GPU 消费 → 注销张量/销毁 graph/context → 释放内存和 GPU 对象 → 关闭连接。实际 SDK 若要求不同顺序，以经过验证的实现和文档为准并记录。

如果引入 D3D12 试验，不能擅自 Close/ExecuteCommandLists 游戏拥有的 command list，也不能等待游戏尚未提交命令的 fence。记录式 API 与同帧 CPU 推理基线的矛盾应在 M9 单独解决，不隐藏在超时重试中。

## 7. 测试矩阵与通过门槛

| 类别 | 试验 | 必须观察 |
| --- | --- | --- |
| 协议 | 分片、截断、超长、溢出、未知版本、错误凭证 | 拒绝有界、无大额意外分配、无崩溃 |
| 帧身份 | 重复、乱序、旧 session、错 generation、错 frame、消费通知丢失/重复/失败 | 不写回错误输出，不提前推进历史，错误归因清楚 |
| 资源 | 非紧密 RowPitch、尺寸/格式变化、错误容量、设备丢失 | 无越界、不复用失效资源 |
| 执行 | 模拟、QNN CPU、HTP 成功、HTP 错误 | 后端与执行证据准确，计数不造假 |
| 故障 | 各阶段断连、daemon 崩溃、故意延迟、上传失败 | 有界返回、失效历史、恢复策略明确 |
| 生命周期 | 重复启动退出、Create/Destroy、第二客户端 | 无跨会话状态，资源回到稳定水平 |
| 真游戏 | 固定场景当前帧输入、HTP 结果、输出消费 | frame 与像素来源可关联，游戏可恢复 |

M4 通过要求 M2+M3 已通过、固定 profile 的真实 HTP 闭环、同帧结果身份验证、故障路径受控且不存在静默旧帧回显。需要报告 CPU/GPU/HTP/IPC 开销，但此节点不承诺可玩帧率或低延迟。

`source_review / build / host_test / device_test / game_test` 分别记录；gate 使用 `not_run / pass / fail / blocked`。mock 回环、Windows CPU QNN、AArch64 交叉编译均不能替代 Odin 3 的 `device_test` 和 `game_test`。

## 8. 交接与停止条件

所选 D 批使用一份短记录：依赖 gate、构建哈希、模型/设备/profile ID、实际后端日志索引、输入/输出摘要、关联帧样例、故障结果、内存清理与恢复命令；不再强制 validation + handoff 成套文件。

记录全部不支持的格式、HDR/DRS/API/多 context 情况。涉及协议变化、独立进程隔离或内存注册策略时写[ADR](../templates/adr.md)，不要只在代码中留下经验常量。

若当前游戏仅触发 D3D12，M4 当前路径应阻塞，回到 M3 选择已验证的候选或正式扩展范围；不能为了让计划继续而返回假成功。若 HTP 失败，保留可工作的 mock 验证并返回 M1/M2 定位，不以 CPU 回退宣称节点完成。

M5 的输入包括：同帧帧包、history 生命周期、重置接口、所有字段映射、现有图像缺陷、失败恢复基线及实际阶段时序。

## 9. 旧执行提示（停用）

> 下列历史提示不得再用于整体启动 M4；当前只从 [D23–D27](DEVICE_EXECUTION.md#m4跨进程同帧闭环) 选择一个叶子。保留它仅供核对技术禁区。

```text
请实施 M4 同帧端到端闭环。先读 docs/STATUS.md、docs/ai/IMPLEMENTATION_GUIDE.md、
docs/architecture/CONTRACTS.md、docs/roadmap/M4-end-to-end.md 和 M2/M3 验收报告。
先确认真实依赖 gate；缺少设备/模型/真实游戏证据时只能完成 host 模拟部分并明确阻塞项。
本次只选择一个可审查的小 PR，不同时做协议、算法改写、零拷贝和 UI。
目标架构为匹配游戏 ABI 的 PE NGX DLL，通过序列化 TCP 连接 AArch64 Linux daemon；
协议使用 draft-0 合同，不传原生指针/COM/fd，不按 payload 长度猜版本。
第一版固定 SDR profile、D3D11、单会话/单 context、单帧在途、同帧同步返回。
用当前帧 readback → TCP → GPU 前处理 → 实际 QNN HTP → GPU 后处理 → TCP → 输出回写。
必须验证 service_instance/session/context/frame/history_generation、尺寸、格式、容量及模型 manifest。
mock/CPU/空间回退明确标记；不能重显旧帧、后台用 CPU 后宣称 NPU，或只伪造帧号证明正确。
遵守所有权与 GPU/NPU 完成边界；网络超时不能并发释放仍在 graphExecute 中的内存。
对无法取消的调用提供隔离/重建策略，失败导致时序不连续时 reset/recreate context。
不要关闭/提交游戏拥有的 D3D12 command list 或等待尚未提交的 fence；此 API 不在首版范围。
加入部分读写、长度溢出、乱序/旧会话、超时、断连、上传失败和重复销毁的针对性测试。
用 source_review/build/host_test/device_test/game_test 与 not_run/pass/fail/blocked 记录结果。
输出变更、实测命令与证据、尚未验证项、验收报告和下一阶段交接；无真机不宣称 M4 通过。
```
