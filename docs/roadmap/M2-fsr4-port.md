# M2：FSR4 v07 / HTP v79 离线移植与连续帧重放

状态：**`not_started`；目标设备 gate `not_run`。** 实施只从 [D12–D18](DEVICE_EXECUTION.md#m2完整-fsr4-模型gpu-流水与离线序列) 选择一个小批次；D12–D13 必须已有真实设备资料，D13 可在 host 生成 context，但不证明设备执行；D14–D18 需要真实设备。无设备准备按 [F 队列](HOST_PREPARATION.md#f真实-fsr-离线分支) 单独验收。前置为 [M1](M1-npu-platform.md)，M3 可并行。本文保留技术依据，旧 M2-A–M2-F 不作为活动批次。

[D 执行队列](DEVICE_EXECUTION.md) · [共享合同](../architecture/CONTRACTS.md) · [历史研究](../reference/2026-09-20-feasibility.zh-CN.md)。必须区分“复现上游重建的 W8A8 研究路径”和“与 AMD 官方完整 FSR4 实现等价”；本节点不承诺后者。

## 1. 目标与非目标

将固定版本的模型转换链、GPU 特征准备、真实 HTP 网络执行、GPU 重建和 history/recurrent 更新移植到 native AArch64 Linux，用离线帧序列重放验证，无需先注入游戏。

- 第一档建议 `960×540 → 1920×1080`，保持上游模型/分辨率参考；资源不足时单独建立 `640×360 → 1280×720` 档。
- 保留固定的 FidelityFX SDK 2.0.0 / `fsr4_model_v07_i8_quality` 来源，先完成移植，再考虑算法升级。
- 建立源模型、转换脚本、量化、context、shader、形状和参考输出相互绑定的 manifest。
- 初始运行模式为同帧、单上下文、同步顺序；每帧成功后再提交历史，不用旧输出冒充新帧。

非目标：不实现 NGX/DLL、Decky、D3D12 桥接或全链路零复制；不自动支持任意倍率、动态分辨率、HDR、超宽屏；不将 XLSR 或单帧空间超分换名当 FSR4；不承诺 FPS/功耗收益。

## 2. 依赖、合法材料和无设备工作

M1 通过后继承准确的 Linux QNN/QAIRT、HTP 架构、SoC 枚举与驱动组合。若 M1 尚未通过，可以先做源码审阅、模型提取、参考图验证、manifest/schema 和 GPU 桌面重放；结果只能分别标记 `source_review` / `build` / `host_test`。

需要自行取得原始 AMD SDK 和 Qualcomm 工具，记录本地来源、版本与哈希；项目不能假定可以重新分发权重、DLC、context、SDK runtime 或固件。源码自有许可证不能自动覆盖这些依赖。模型资产存于用户配置的本地目录，生成脚本与非敏感清单可以提交。

离线输入须带来源和语义：可先合成平移/静态图案，也可使用后续获准采集的游戏帧；保存颜色、MV、jitter、曝光、reset 及必要 metadata。只有 RGB 视频不足以构成完整时序参考输入。未获得官方参考输出时，应明确“未做官方等价对比”。

## 3. 按顺序阅读上游源码

以下均固定于 `fsr4-hexagon` 的 `8c7a972ab70e5693828a856da71ce711232af463`：

1. [模型 README](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/README.md)、[权重提取](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/extract/build_weights.py)、[模拟器](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/sim/fsr4_sim.py)：先确认权重排列与来源自检。
2. [参考 ONNX 构图](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/onnx/build_onnx.py)、[clip-free Q/DQ](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/onnx/build_qdq_clipfree.py)、[dummy 输出](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/onnx/add_dummy_output.py)：逐一记录 workaround 和当前 QAIRT/v79 是否仍需要。
3. [融合特征 shader](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/shaders/features_fused.comp)、[postA](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/shaders/posta.comp)：确定 GPU/NPU 分区、颜色域、首层卷积和时序状态更新。
4. [qnn_service.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/qnn_service.c)、[live_daemon.c](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/live_daemon.c)：以实际 `.c` 控制流和 shader 为准，头文件旧注释不代表当前生产行为。
5. [Android 构建](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/build.sh)、[生产启动脚本](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/launch_production.sh)：圈出 Android NDK、libandroid、AHardwareBuffer、目录和 v73 假设。
6. [白皮书限制](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/WHITEPAPER.md#L202)、[第三方材料](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/THIRD_PARTY.md)：保留质量/延迟边界和声明。

上游网络是改造后的 W8A8 分区图；NPU tensor 不是普通三通道 RGB。1080p 参考合同为 INT8 NHWC `[1,540,960,16] → [1,1080,1920,8]`，最终必须由实际 graph 元数据确认。裸输入/输出约 8.29 MB / 16.59 MB，尚未包括 GPU 历史、临时缓冲和权重。

## 4. 建议模块与实现选择（尚未实现）

| 拟议路径 | 职责 |
| --- | --- |
| `tools/model/extract.py` | 接受显式 SDK 路径，权重提取和哈希，不写死开发者目录 |
| `tools/model/convert.py` | 固定工具环境、参考图/量化/prepare 的分阶段执行 |
| `tools/model/manifest.py` | 收集 graph/tensor/量化/shader 元数据并验证一致性 |
| `tools/model/replay/` | 读取 frame bank、逐阶段 dump、数值与序列比较 |
| `runtime/qnn/` | 复用 M1 loader/context，添加本模型 tensor 绑定 |
| `runtime/gpu/` | Linux EGL/GLES 上下文、特征/重建 shader、同步与 staging |
| `runtime/core/` | 模型档案、帧身份、history 生命周期、顺序调度 |
| `docs/models/fsr4-v07-v79.md` | 锁定组合、质量差异、生成步骤和资产取得说明 |

首选保留 GLES compute，以缩小与上游的差异；验证 Linux EGL 创建方式（surfaceless/pbuffer）和所需扩展，不能假定 Android EGL 扩展可用。只有确实缺失能力或后续性能证据支持时才改 Vulkan compute，并用 ADR 说明；不要同时更换模型、着色器算法、API 和异步调度。

初始数据流：GPU feature → 明确同步 → CPU staging/合法 QNN buffer → HTP → CPU staging → GPU postA/重建。关闭 AHardwareBuffer 专属快路径，内存注册若需要则复用 M1 已证明方式。QNN `memRegister` 不支持的 FD 类型必须报错，不能复制 Android ION/dma-buf 假设。

## 5. 分批实现与输出

### M2-A：冻结模型与参考计算

1. 固定 AMD SDK、上游 commit、提取脚本和模型目录哈希；参数化输入/输出路径，避免修改个人绝对路径。
2. 提取权重和 graph_spec，完成上游提供的交叉检查；保存每阶段输出摘要及工具版本。
3. 运行 simulator/参考图，核对层参数、weight layout、padding、激活和张量排列。
4. 为合成输入建立可重放的参考 tensor bank；不要只对自己的输出再计算 hash 就称数值正确。

输出：可复现提取步骤、参考张量、资产清单。原始权重不随代码自动提交。

### M2-B：转换、量化与 v79 context

1. 建参考 ONNX，确认 graph 输入输出名字、NCHW/NHWC 转换和浮点/量化边界。
2. 生成参考 DLC/编码资料，再按上游依赖关系生成 clip-free Q/DQ 图；不能在没有 encoding dump 时编造 scale/offset。
3. 针对当前 QAIRT/v79 测试 Clip、ReLU、dummy output 等 workaround；每个保留/删除决定用对照实验或编译器日志支撑。
4. 用固定校准 bank 量化，保存校准列表、样本摘要、参数、逐 tensor encoding 与随机种子。
5. 为 M1 确认的 SoC/HTP 生成 context；实际 SDK 工具、backend 名称和参数以锁定版本帮助/文档为准。
6. 从 DLC/context 元数据读取内部 graph 名，核对 backend extensions 配置真正生效；不能只看工具返回 0，也不能把文件名误当固定 graph 名。

输出：ONNX/DLC/context 的本地哈希、构建日志、manifest 草案。离线生成成功只算 `build`，不算 HTP 实测。

### M2-C：先验证 NPU 子图

1. 复用 M1 探针，输入参考量化 tensor；从 QNN 元数据校验实际 signedness、shape、dtype 和 encoding。
2. 量化/反量化按所选 SDK 的 encoding 定义实现，记录其公式和 offset 含义；不得将 offset 与 zero-point 不经转换混用。
3. 对比参考 INT8/QDQ 图与真实 HTP 输出，记录 max/mean absolute error、饱和比例及异常值。
4. 单独核验 dummy 输出与真正输出，防止拿第一个输出索引碰巧“能显示图”便通过。
5. 给出预先确定、基于量化误差的容差；不能看到结果后任意放宽，也不要无依据要求跨后端 bit-exact。

输出：固定 tensor bank 的 device_test 报告、误差预算、真实 HTP 执行证据。若此批失败，暂不调 GPU 画面掩盖问题。

### M2-D：GPU 前后处理 Linux 移植

1. 抽出平台分配/上下文/同步接口，移除 Android 头文件、libandroid 链接和硬编码路径。
2. 分别重放颜色转换、重投影/特征、首层卷积/量化、NPU 输出解码、postA、可选 RCAS。
3. 在每个边界保存 shape、stride、格式和摘要，校验 GPU fence/barrier 完成后 CPU 才读取，CPU 写完后 GPU 才继续。
4. 把 shader 常量、卷积权重/seed、编码参数和输入输出尺寸关联同一 manifest，不允许只有 context 换了而 shader 未换。
5. 建立独立 reference 计算或上游捕获对照；图形驱动不同带来的浮点差异与真正通道错位分开判断。

输出：Linux GPU harness、逐阶段对照及内存生命周期说明。共享 DRAM 和 staging 成功均不代表零复制。

### M2-E：连续帧与 history 合同

1. 每个 context 独立拥有 history/recurrent；将 `session_id`、`context_id`、`frame_id`、`history_generation` 绑定至每个中间结果。
2. 先串行处理 `pre(n) → NPU(n) → post(n) → commit history(n)`。优先使用 current/next 双缓冲，全部必要阶段和离线输出校验成功后交换；接入游戏后还须遵循 M4 消费确认。上游 postA 可能直接更新 history/recurrent，若保留 in-place 路径，后续 RCAS/下载失败也必须使整套历史失效，等待在途工作结束后初始化并换代，不能仅跳过 commit 标记。
3. 显式 reset、模型/尺寸切换、断连重建、不连续帧和挂起恢复采用明确重置策略；旧 generation 的结果必须丢弃。
4. 用已知平移方向验证 MV 单位/方向/Y 轴和 jitter；用曝光跳变验证 pre-exposure 语义，禁止长期固定 1 而不报告。
5. 保存 API 提供但当前算法未消费的 depth/mask 元数据，并在能力声明写明。没有证据时不凭空添加深度网络输入，也不能声称完整 FSR4 语义已还原。

为 postA 完成后、RCAS 中、输出下载时分别注入失败，验证下一帧不会读取部分更新历史。generation 由原生 context 所有者统一分配，遵循公共合同的 reset/换代规则。
6. 建立静态、平移、遮挡/显露、切镜头、曝光变化、reset 和尺寸拒绝等序列，检查连续帧而非只看静态截图。

输出：离线时序重放报告、reset 用例、历史所有权和失败恢复说明。

### M2-F：选择产品候选模式

`research-compatible` 用来对照上游算法、量化与颜色处理；`temporal-correct` 用来接入显式 reset/当前帧合同和可审查修正。两者分别命名、分别记录差异与画质，不共享“通过”的结论。为了复现论文另外测试多帧异步时，必须单独记录 frame age，不能替换本节点同步基线。

输出：可交给 M4 的固定档、已使用/未使用输入字段、错误行为、重放包和模型 manifest；不要求性能已经适合游戏。

## 6. 拟议 manifest 与重放输入

以下是**未运行的格式示例**，不是可直接加载的模型清单。哈希/量化等关键值缺失时加载器必须拒绝。

```json
{
  "schema_version": "draft-0",
  "example_only": true,
  "model_manifest_id": "example-fsr4-v07-v79-1080p",
  "device_profile_id": "example-odin3-baseline",
  "evidence_level": "source_review",
  "algorithm": "fsr4-v07-research-port",
  "source_model": {"sdk": "FidelityFX SDK 2.0.0", "model": "fsr4_model_v07_i8_quality"},
  "render_size": [960, 540],
  "display_size": [1920, 1080],
  "target": {"soc_model": null, "htp_arch": 79, "device_verified": false},
  "toolchain": {"qairt_version": null, "converter_commit": null},
  "graph": {
    "name": null,
    "inputs": [{"layout": "NHWC", "dtype": "int8", "shape": [1, 540, 960, 16], "quantization": null}],
    "outputs": [{"layout": "NHWC", "dtype": "int8", "shape": [1, 1080, 1920, 8], "quantization": null}]
  },
  "artifacts": [],
  "validation_gate": "not_run"
}
```

frame bank 每帧至少描述：上述四个帧身份字段、输入图像路径/格式/row pitch/有效区域、MV 编码/尺度/方向、jitter、reset、曝光、输入时间戳；文件内容用摘要绑定。时间戳的单位/时钟域写明，不能比较不同机器未校准的 wall clock。

例中的 shape 和 HTP 79 是目标预期；`device_verified: false` 表示没有设备确认。实际 manifest 还须记录 tensor 名称、dummy 输出、全部资产及编码 convention；示例不能替代运行时枚举。

本节点文件格式和以后 M4 的 wire 格式分离；任何网络协议使用 draft-0 草案要求的显式序列化与长度检查，禁止把 C/C++ struct 内存直接发到线上。

## 7. 现有只读检查与拟议执行命令

以下为 **Linux 开发机上的现有只读命令**，先设置上游 checkout 的真实目录；不执行依赖安装或模型转换：

```bash
FSR4_SRC='/absolute/path/to/fsr4-hexagon'
git -C "$FSR4_SRC" rev-parse HEAD
git -C "$FSR4_SRC" status --short
rg -n 'ROOT|fsr4_model|quality' "$FSR4_SRC/model/extract/build_weights.py"
rg -n 'AHardwareBuffer|QNN_MEM_TYPE|graphExecute' "$FSR4_SRC/daemon/qnn_service.c"
rg -n 'history|recurrent|reset' "$FSR4_SRC/daemon/shaders/posta.comp" "$FSR4_SRC/daemon/live_daemon.c"
```

上游 `model/README.md` 包含实际转换命令，但依赖用户资产、固定 QAIRT Python 环境和具体 graph 名，先审阅本机版本再生成可执行计划。不要在文档示例里写一个虚构 context 文件然后宣称工具完成。

以下是**拟议命令，当前不存在**；实现后先核对帮助和路径，再运行：

```text
python3 tools/model/extract.py --sdk-root <user-sdk> --output <new-artifact-directory>
python3 tools/model/convert.py --manifest <build-manifest.json> --stage <explicit-stage>
python3 tools/model/manifest.py verify --manifest <model-manifest.json>
fsr4hex-replay --manifest <model-manifest.json> --sequence <bank.json> --mode research-compatible --report <new-report.json>
```

`fsr4hex-replay` 是本节点建议的独立离线 harness 名称，尚未存在；不替代未来 `fsr4hex-daemon`。转换器必须保存实际 argv/版本/退出码，并在中途失败时保留可诊断阶段，不能自动尝试不同 SDK 直到“成功”。

## 8. 验证矩阵与通过门槛

| 层级 | 必要验证 | 证据边界 |
| --- | --- | --- |
| `source_review` | 分区图、许可、GPU/NPU 边界、历史顺序 | 设计可审阅 |
| `build` | 权重提取自检、图编译、context 和 shader 构建 | 有产物，不证明设备可运行 |
| `host_test` | simulator/ONNX 对照、schema、GPU stage、错误输入 | 参考与移植逻辑可信，不证明 HTP |
| `device_test` | NPU tensor 对照、GPU+NPU 连续帧、reset | 此固定组合的离线 FSR4 路径通过 |
| `game_test` | 本节点无需实施，交由 M4 | 不宣称游戏兼容或性能收益 |

M2 通过必须具备：有效 M1 报告；完整且可验证的模型 manifest；真实 HTP tensor 对照；至少一条固定分辨率 Linux GPU/NPU 顺序闭环；上述关键时序序列有正确结果；失败/重置不使用旧 generation；图像差异与未消费字段明确披露。

验收前为每阶段登记容差和序列检查标准。建议至少 300 帧连续序列覆盖静态/运动，并为 reset/切镜头/曝光变化单独建立短序列；这是可调整但必须预先记录的工程门槛。PSNR/平均误差只辅助数值定位，不能代替对重影、闪烁、遮挡和细线的时序检查。

以下情况暂停移植宣告：拿不到合法模型材料、SDK/HTP 不匹配、quant encoding 缺失、dummy 输出混淆、CPU 回退、序列历史泄漏、显著错误无法定位。缺少官方 FP16 对照只限制等价性声明；不得将自建 INT8 对照通过写成官方质量等价。

## 9. 批次记录与旧提示

所选 D 批只需一份短记录；原始数据在本地 artifact 目录按需创建。只有影响公共 ABI、同步或许可的决定才需要 ADR，不再强制 validation + handoff 成套文件。

交接至少包含：设备/模型 ID、工具和 shader SHA、资产本地取得方式、实际 graph/tensor metadata、量化公式、参考 bank、逐阶段误差、当前输入限制、history 提交/重置规则、阶段耗时及其测量边界、M4 可调用的 API 和仍缺失能力。报告实际 NPU 时延与整帧重放时延，不把前者换算成整个系统 FPS。

> 原可复制提示已停用；它会按完整 M2 顺序连续开工。只从 [D12–D18](DEVICE_EXECUTION.md#m2完整-fsr4-模型gpu-流水与离线序列) 选择一项，技术约束以上文为准。
