# M5 · 时序画质、历史状态与恢复

状态：**`not_started`；真实设备、游戏、画质与稳定性 gate 均 `not_run`。** 实施只从 [D28–D29](DEVICE_EXECUTION.md#m5时序画质与恢复) 选择一个小批次。本节点验证连续游戏帧的语义是否正确，继承 M4 同帧复制基线；技术正文不作为第二套队列。

- 前置依赖：M4 固定 profile 的真实 HTP/游戏闭环与故障控制已通过。
- 交付：可重放场景集、字段映射表、历史状态机、逐阶段/连续帧画质报告，以及 `docs/validation/M5/YYYY-MM-DD-<work-package>.md`。
- 范围：一个已验证游戏/API/固定分辨率 SDR profile；更换模型、量化、着色器或关键映射必须重新验收。
- 默认建议：一次至少 30 分钟的连续稳定试验，并覆盖可重复的切场景、暂停恢复、重连与重新创建；这只是起始门槛，不代表完整可靠性认证。

[D 执行队列](DEVICE_EXECUTION.md) · [跨组件合同](../architecture/CONTRACTS.md) · [项目状态](../STATUS.md)。文中字段为拟议 `draft-0` 合同，未冻结 ABI。

## 1. 目标与禁止混淆的结论

需要证明输入语义、历史推进与恢复策略在限定场景中成立；发现模型本身的局限也属于有效结果。不是所有残影都由传输导致，也不是开启锐化后截图更清晰就代表重建更准确。

“复现上游 W8A8 实现”“Linux 移植与同一量化参考一致”“与官方 FP16/GPU FSR4 动态画质相同”是三个不同命题。本项目只能在对应参考和实验具备时分别报告，不能互相替代。

本节点不直接追求性能优化，不引入共享内存、多帧流水、DLSS 帧生成或自动 HDR/DRS 支持。若修复时序需改模型或算法，单独锁定新 manifest、说明与原参考的差别，不延用原分数。

## 2. 必读来源与审计起点

| 固定来源 | 已知边界及阅读目标 |
| --- | --- |
| [full_proxy.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/proxy/full_proxy.c) | color/MV/jitter 传递；depth 未实际消费、游戏 reset 未完整传递、exposure 路径有限 |
| [live_daemon.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/live_daemon.c) | MV/jitter 调整、自动曝光选项、切场景启发式、重连 invalidate |
| [features_fused.comp](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/shaders/features_fused.comp) | 特征构建、history 重投影、量化与首层卷积 |
| [posta.comp](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/shaders/posta.comp) | 重建、history 与 recurrent 更新；不是纯单帧 RGB 模型 |
| [qnn_service.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/qnn_service.c) | 初始化种子、reset/invalidate、GPU/NPU 状态与时序顺序 |
| [WHITEPAPER.md](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/WHITEPAPER.md) | 静态图、INT8 自洽、帧年龄和未评估的 FP16 动态质量边界 |
| [fsr4_sim.py](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/sim/fsr4_sim.py) | 数值参考；核对与生产 split 路径的差异，不能假设完全等价 |

上游用运动阈值推断 reset，并不能替代游戏的显式 reset；阈值可能把正常移动当作切场景。此节点先保留并验证来源字段，再决定启发式是否需要以及适用边界。

## 3. 输入、模块与产物

输入包括 M4 的帧包和关联日志、M2 的模型/shader/量化 manifest、M3 的字段映射、当前已知缺陷、固定游戏存档或基准流程。场景捕获要记录游戏构建、图形设置、相机路径、帧间隔和曝光状态；不能只保存没有 metadata 的最终截图。

```text
runtime/core/temporal/        # context 生命周期、generation、reset 原因与连续性
runtime/gpu/                 # MV/jitter/exposure 映射与历史缓冲操作
adapters/ngx/                # 游戏参数存在性、reset/曝光/深度保留
tools/replay/                # 连续帧重放、截断/重排/重置注入
tools/quality/               # 对齐、差分、时域指标与报告生成
tests/temporal/              # 合成运动、曝光、遮挡、状态机测试
tests/fixtures/temporal/     # 可公开的合成序列与生成器
docs/validation/M5/          # 日期-工作包报告及同名 -handoff.md
```

PE 代理只按游戏 ABI 提供输入/输出边界，原生 AArch64 Linux 运行时拥有 GPU/HTP 时序状态。不能把 temporal buffer 指针或 PE 资源句柄直接塞进跨进程协议。

## 4. 需要先写清楚的状态机

```text
Created / Invalid → InitializeHistory → Ready(generation g)
Ready(g) → Execute(frame n, g) → PrepareNextHistory → PendingConsumption(n, g)
PendingConsumption + valid result_consumed(success) → CommitHistory(n, g) → Ready(g)
PendingConsumption + failure / timeout / disconnect → Invalid
Ready(g) + explicit reset / discontinuity → Invalidate → Ready(new generation)
Execute + failure / disconnect / uncertain output → Invalid
任意状态 + Destroy → 等待/隔离在途工作 → Released
```

generation 按公共合同建议由原生 context 所有者统一分配，并由 M4-A ADR 冻结 reset 请求/回复流程；不得由客户端与服务端各自自增。收到旧 generation 的输入或响应必须拒绝。重置需同时覆盖颜色 history、recurrent、上一帧 jitter/exposure、帧连续性信息和算法额外状态，不能只清空一张纹理。

完成 n 并收到有效写回消费确认后，n+1 才使用 n 的有效历史；确认指图形 API 可消费，不是实际显示。优先用 current/next 双缓冲；in-place 更新的部分失败必须完整失效，不能仅跳过 commit 标记。首帧与 reset 帧采用经验证的初始化策略，不能引用上一局游戏。游戏输出回写失败、响应或确认丢失时，已有 history 不再代表可信连续序列，必须按 M4 恢复策略失效。

| 事件 | 预期处理 |
| --- | --- |
| 游戏显式 reset | 在处理该帧前应用，记录来源与 generation 变化 |
| 模型/分辨率/格式变化 | 当前固定 profile 先拒绝；若重建，销毁旧 context 并重新协商 |
| 新会话、重连、游戏重启 | 新 context 或完整失效，不跨会话保留历史 |
| 重复/乱序/缺帧 | 拒绝或明确重置策略；不可悄悄推进两次或使用错误前帧 |
| 暂停/恢复、长时间无输入 | 区分没有新帧与帧时间不连续；按 profile 中可测试规则处理 |
| 自动切场景判断 | 附加保护；不能覆盖/丢弃显式 reset，也不能每帧触发来掩盖 MV 错误 |

## 5. 可审查的小 PR 顺序

### PR M5-A：参数映射与可重放帧包

1. 补齐颜色、MV、jitter、reset、exposure/pre-exposure、帧时间及 depth 的存在性和来源记录。
2. 区分游戏原始值、归一化值与算法实际消费值，保存转换顺序及对应 profile 版本。
3. 每个帧包关联 `device_profile_id / model_manifest_id / service_instance_id / session_id / context_id / frame_id / history_generation`。
4. 记录格式、stride、有效区域和颜色空间；明确 shader 接收的是线性值、压缩值还是已预曝光颜色。
5. 从同一帧包重放 Linux 后端，确保不依赖当前游戏时钟、随机种子或未初始化的全局状态。

完成条件：离线连续帧能复现已观察缺陷，输入转换过程可追溯；不能仅输出最后 RGB 文件。

### PR M5-B：历史状态与 reset

1. 为 context 增加显式状态、generation、上一成功帧号及 reset 原因，而非散落布尔开关。
2. 单元测试首帧、正常连续、显式 reset、重连、丢帧、重复帧、模型重建与失败后的恢复。
3. 在每个 GPU/NPU 阶段以及 postA 后、下载/写回和消费确认处注入失败，证明半更新或未确认 history 不会被下一帧当作有效历史。
4. 对初始化种子与清零策略逐项核对 M2/上游算法；不要假设所有 recurrent state 都应填零。
5. 保留 reset 计数和原因分布；静止/匀速场景频繁 reset 视为诊断信号。

完成条件：状态转移与像素序列一致；任何新 session 都不能重用另一 session 的图像历史。

### PR M5-C：MV、jitter 与曝光语义

1. 用带已知位移的纹理测试 MV 是 current→previous 还是相反、单位是像素还是归一化、尺度作用在哪个分辨率。
2. 分别测试 X/Y、正负、不同速度和边界外采样；“某个场景看起来更清晰”不能替代方向判定。
3. 固定相机并使用已知 jitter 序列，验证符号、单位、Y 轴、当前/上一帧关系及是否已包含在 MV 中。
4. 不重复消除或添加 jitter；对游戏没有提供的量只能写明有限支持条件，不能长期硬编码成正确值。
5. 构造恒亮/渐变/突变曝光序列，检查 pre-exposure 的应用与恢复次序，以及历史是否按同一曝光域重投影。
6. 游戏曝光、算法内部自动曝光、上游默认 expo=1 分开命名；只能采用有依据且经过测试的一条路径。

完成条件：合成参考通过预先设定的误差界限，真实场景没有因尺度/符号错误产生持续拖影或亮度泵动。

### PR M5-D：depth、遮挡与可选输入评估

1. 从实际 NGX 调用保留 depth 描述和使用状态，核对分辨率、格式、反向深度、无限远/投影约定及有效区域。
2. 查明当前上游 split 算法在哪些阶段具备/缺少遮挡判断；“捕获到 depth”不等于算法已正确消费。
3. 评估背景显露、前景遮挡、薄边界与透明物体；分离没有深度路径造成的算法限制与错误 MV 的表现。
4. 若要增加深度/mask 辅助逻辑，先写 ADR、参考公式、输入归一化与合成测试，再独立验证画质影响。
5. 不把 depth 任意追加到固定 16 通道 NPU 输入，也不把某个 mask 当成模型原本训练过的通道。
6. 首版无法支持时，保留 `present/consumed/validated` 的区别，在 profile 与报告公开限制；不宣称完整 FSR4 语义等价。

完成条件：有可审计的已消费字段表和缺失项影响分析。必要输入无法正确映射且导致不可接受画质时，该 profile gate 失败。

### PR M5-E：场景画质与恢复稳定性

建立固定序列清单，逐个重放并在实机采集。最后运行至少 30 分钟的持续游戏试验，记录实际起止时间、帧数、热状态、内存/句柄/线程数、错误/reset/回退数和人工事件时间点。

30 分钟没有崩溃不能单独通过：还要检查持续旧帧、历史污染、亮度异常、内存递增、反复重连及错误被回退掩盖。未达到时长就报告实际时长，不补写通过。

## 6. 最小场景矩阵

| 场景 | 隔离的问题 | 主要观测 |
| --- | --- | --- |
| 静止相机与细纹/栅栏 | jitter、历史积累、锐化 | 闪烁、爬行、过锐边缘、reset 频率 |
| 匀速平移与快速转镜 | MV 方向/尺度与帧身份 | 持续残影、错误重投影、边缘拖尾 |
| 前景横移、背景显露 | 深度/遮挡处理 | 新显露区域恢复速度、历史泄漏 |
| 粒子、透明表面、反射 | 引擎 MV/可选 mask 局限 | 透明物体残影、细节丢失、失败范围 |
| 亮暗场切换和爆闪 | pre-exposure/曝光/reset | 泵动、裁剪、历史亮度不匹配 |
| 切镜头、读档、进出菜单 | reset 与 context 生命周期 | 旧场景污染、首帧异常、重复重置 |
| HUD、字幕与准星 | 超分输出与后处理位置 | 错帧叠加、拖影；确认 HUD 是否已在输入内 |
| 暂停/恢复、窗口切换、重连 | 连续性与故障恢复 | generation 变化、失效资源、恢复路径 |
| HDR/DRS/不支持比例尝试 | 能力边界 | 创建/换档受控拒绝，不静默低精度输出 |

合成序列用于确定转换正确性；真实游戏用于确认输入语义与可接受画质。两类都需要，不能只用最干净的合成图做最终展示。

## 7. 对照组、指标与验收边界

对照至少包括原生目标分辨率、相同低渲染分辨率的已知空间路径、当前 FSR4 NPU 同帧路径，以及可取得的同模型参考。保持相机/帧序列、分辨率、锐化、曝光和色彩转换一致；无法对齐时写清比较限制。

逐阶段报告平均/最大误差、分位数、异常值/NaN/Inf 与量化饱和情况。最终图可用 PSNR/SSIM 辅助比较，但不要把静态均值当作动态等价；补充连续帧差分、稳定区域闪烁、残影持续帧数与最差片段。

容差必须来自 M2 数值基线、数据类型和参考实现，记录选择依据。不可为了让新输出通过而事后扩大阈值，也不要设一个没有依据的“PSNR 大于某值即等同官方 FSR4”。有意算法变化与移植误差单独列出。

| 验收维度 | 通过要求 |
| --- | --- |
| 帧与历史 | 每帧身份正确；没有跨会话污染；reset 与 generation 可追溯 |
| 输入语义 | MV/jitter/exposure 已验证，depth/可选字段是否消费与限制明确 |
| 数值 | 同一 manifest 的阶段误差在事先记录界限内，无未解释的异常数据 |
| 动态画质 | 必测场景有连续帧证据；严重持续残影、闪烁、切场景污染无未处置项 |
| 恢复 | 断连/回写失败/重建不继续使用旧历史；不可恢复情况明确停用 |
| 稳定性 | 达到实际记录的持续时长；无持续资源增长、死锁或静默错误 |
| 能力边界 | 未支持 HDR/DRS/API/分辨率被拒绝，状态与实际运行模式一致 |

公开结论限定到游戏构建/API/兼容栈/设备/模型/profile 组合。M5 通过不代表更快、更省电、低输入延迟或所有游戏可用；这些需要 M6 和后续覆盖验证。

## 8. 数据样例、所有权与回退

```json
{
  "schema_version": "draft-0", "example_only": true,
  "device_profile_id": "example-device", "model_manifest_id": "example-manifest",
  "service_instance_id": "service-example-1", "session_id": "s-1", "context_id": "c-1",
  "frame_id": "108", "history_generation": "4",
  "reset": {"requested": true, "source": "game", "applied_before_frame": true},
  "depth": {"present": true, "consumed": false, "validated": false},
  "exposure": {"source": "unverified", "pre_exposure": null},
  "sequence": "scene-cut-example", "evidence_level": "game_test", "gate": "not_run"
}
```

该例为记录语义示意，不是测试结果。真实证据等级仍为 `source_review / build / host_test / device_test / game_test`，gate 为 `not_run / pass / fail / blocked`。

history/recurrent 与其上一帧 metadata 由同一 context 所有；执行尚未完成时不能释放或由另一会话覆盖。清理沿用 M4 在途资源规则。测试捕获只保存所需片段和摘要，公开数据使用可公开的合成内容或符合权限的样例。

画质错误不能一律通过重置每帧来“修复”，这样会破坏时序重建目标。若必要字段缺失、输入超出能力或画质不可接受，应停用该 profile，或选择已验证且清楚标注的同帧回退；禁止悄悄切回旧帧缓存。

## 9. 无硬件工作与交接

无设备时可以完成状态机、生成器、重放格式、字段映射审查、数值比较和故障测试；如果只有 CPU/reference，则只能记录对应 evidence。不能宣称 Snapdragon HTP 数值一致、真实游戏动态画质可接受或 30 分钟实机稳定。

所选 D 批用一份短记录保存场景索引/哈希、manifest、映射表、阈值与理由、最差片段、reset 日志、缺陷分级、稳定试验数据及恢复步骤；只有必要决策另写 ADR，不再强制独立 handoff。

移交 M6 时锁定已通过的画质 profile，说明哪些优化会触发重验：流水改变、精度/量化、颜色格式、history 布局、MV/jitter/exposure 转换、模型/着色器版本。不能在性能分支中静默降低画质后仍沿用 M5 结论。

## 10. 旧执行提示（停用）

> 下列历史提示不得再用于整体启动 M5；当前只从 [D28–D29](DEVICE_EXECUTION.md#m5时序画质与恢复) 选择一个叶子。保留它仅供核对技术禁区。

```text
请实施 M5 时序画质与恢复。先读 docs/STATUS.md、docs/ai/IMPLEMENTATION_GUIDE.md、
docs/architecture/CONTRACTS.md、docs/roadmap/M5-temporal-quality.md 和 M2/M3/M4 报告。
在 M4 的固定 SDR、同帧、单在途基线上工作，本次只完成一个可审查小 PR。
目标为 Odin 3 / Snapdragon 8 Elite / 经 M0 核对的 Armada 栈；不猜测游戏/ABI/模型参数。
优先补齐原始值→归一化值→算法消费值的映射与可重放帧包，再实现历史/reset 状态机。
每个 context 独立保存 history/recurrent、上一帧 jitter/exposure 与连续性；
使用合同规定的 generation 权威方，断连/丢帧/回写失败/模型变化后按规则失效。
用合成平移验证 MV 方向/单位/Y 轴/尺度，用已知 jitter 验证重投影，用曝光序列验证色彩域。
保留游戏显式 reset；运动阈值只作经验证的辅助，不能每帧 reset 掩盖错误。
审查 depth/遮挡缺口并区分 present/consumed/validated；不把 depth 随意加入固定 NPU 通道。
建立静态细节、快速转镜、遮挡、透明、HUD、切场景、曝光和恢复的连续帧矩阵。
阈值在比较前依据 M2/参考固定；静态 PSNR、INT8 自洽、锐化清晰度均不能证明官方 FSR4 等价。
保持 HDR/DRS/未知尺寸明确不支持；无硬件可做 host/reference 测试，不伪造 HTP/游戏/30 分钟结果。
有实机时至少进行实际记录的 30 分钟稳定试验，检查资源增长、reset/回退、旧帧与恢复事件。
完成后报告改动、证据等级和 gate、已验证映射、未解决画质缺陷、复现命令及交接。
不要提前做性能优化或 UI，不把 M5 通过称为更快、更省电或所有游戏已兼容。
```
