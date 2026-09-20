# 无设备阶段二：资产、工具链与离线参考

评估日期：2026-09-20。用户已授权在 H1–H4 完成后规划新的 Windows / CPU 批次。本页定义 P1–P9；实际进度以 [STATUS](../STATUS.md) 为准。规划完成不代表依赖已下载或模型已运行。

## 1. 当前进展与剩余距离

基准为 `74d5ef28cfdf8f65150bfd7abfdc8d384a8efa93`。本轮 Windows `.venv`（Python 3.12.14 / AMD64、jsonschema 4.26.0）执行 `-m unittest discover -s tests -p "test_*.py"`：退出 0，104 项中 103 通过、1 skipped（普通文件 symlink 权限不可用）。

| 已有能力 | 实际边界 | 接下来需要的能力 |
| --- | --- | --- |
| M0 采集器、schema、脱敏和 fixture | 主机测试已跑；Linux/设备行为仍未实测 | 接设备后采集真实镜像、ABI、FastRPC 信息 |
| H2 tensor/manifest 校验 | `host-synthetic-manifest-v1` 强制 synthetic ID；没有真实资产来源、哈希或模型装载合同 | 独立的资产登记/核验工具，保留 H2 fixture 约束 |
| H3 量化和整数重投影参考 | 小算子、独立预期；没有完整 FSR 网络、特征和重建 | 自有小图、CPU 推理参考，资产可用后再做 FSR 子图 |
| H4 生命周期 harness | Python 同步计算加显式事件；candidate history 是输入快照，资源是 Python 对象 | 资源预算/背压和有实际变化的候选状态测试；真实 GPU/NPU 所有权仍待后续 |
| Windows Python 环境 | 本机 `.venv` 可用，系统 Python 3.9 未修改；基础解释器来自 Codex 缓存 | 可由显式 Python 路径重建的通用入口，不能依赖个人缓存路径 |

本轮仅检查仓库约定的 `sdk/`、`sdks/`、`models/`、`weights/`、`research/`、`local/` 及 QNN/QAIRT/AISW SDK 环境变量：目录均不存在、变量未配置。这证明项目尚未登记/部署这些依赖，不能据此断言整台电脑没有 SDK。未全盘查找。

H 队列 complete 表示既定主机验收完成；项目仍处于移植前准备阶段。没有可用超分运行时、真实模型提取结果、NPU 服务或游戏接入，无法给出可信的整体完成百分比。

## 2. 要准备哪些材料

| 材料 | 获取与核对方式 | 无设备时可做什么 |
| --- | --- | --- |
| 上游研究源码 | 固定 `fsr4-hexagon` 的 `8c7a972ab70e5693828a856da71ce711232af463`，保存许可证和变更说明 | 审阅/参数化提取与构图脚本；不执行 Android 启动/解锁脚本 |
| AMD v07 INT8 quality 源材料 | 从合法取得的 SDK 检查实际文件及适用条款；官方发布入口见下文 | 核对文件、哈希、版本，满足条件后提取；仅有 DLL 时报告缺失 |
| Qualcomm QAIRT/QNN | 从官方 Software Center 取得并锁定一套 SDK；研究上游引用 2.50，尚未选成本项目已验证版本 | Windows 工具安装、help/version、可支持的转换/量化和元数据导出 |
| NumPy / ONNX / CPU 推理库 | 根据所选脚本、SDK、Python 的兼容组合锁定，分环境安装 | 小图参考、图结构检查、真实资产可用后的网络对照 |
| Linux ARM64 runtime / HTP 库 | 只登记 SDK 合法提供的候选文件，记录 ELF、依赖和目标信息 | Windows 上只读解析；装载/执行兼容性等待目标镜像 |
| 平台 FastRPC、CDSP 固件及驱动 | 由目标设备/BSP 提供，版本目前 unknown | 写待核查清单；没有部署目标，当前不下载通用固件代替 |

AMD 官方 FSR4 发布说明描述的是签名 DLL 和有限源码，不能把“下载了 SDK”直接等同“拿到了提取所需模型”。[AMD 发布说明](https://gpuopen.com/learn/amd-fsr4-gpuopen-release/)。

固定上游提取脚本实际读取 `internal/shaders/fsr4_model_v07_i8_quality/` 下的 `initializers.bin`、`passes_1080.hlsl`、`pre.hlsl`、`post.hlsl`，还交叉核对 `dx12/ffx_provider_fsr4_dx12.cpp`。路径相对于 SDK 的 `Kits/FidelityFX/upscalers/fsr4/`。使用 `FIDELITYFX_SDK_ROOT` 指定来源；文件名和目录存在只是预检，不能替代许可、内容和版本核验。[提取脚本](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/extract/build_weights.py)。

QAIRT 是工具与 runtime 的集合，QNN 是相关接口/组件；不能将它们视为单个可随意替换的 DLL。上游记录了 Windows 转换路径和 Python 3.12 环境，同时把 HTP 序列化放在设备上，并注明其离线 prepare 路径需要 Linux host。这只是固定上游组合的证据，不推断所有 SDK 版本的能力。[上游模型说明](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/model/README.md)。

官方 [Software Center](https://softwarecenter.qualcomm.com/catalog/item/Qualcomm_AI_Runtime_Community) 是 SDK 获取入口；本轮未登录下载、未验证其具体可获取版本。Qualcomm 的 [AppBuilder 环境说明](https://github.com/qualcomm/qai-appbuilder/blob/main/docs/user_guide.md)提供 SDK 获取和 runtime 布局参考，其中 WoS 运行示例不能当作本机 AMD64 或 Armada 支持证明。最终以取得的 SDK 内本版本 setup 文档、发行说明和实际 `--help` 为准。

许可检查记录来源与适用条款，不做宽泛法律结论。不同来源文件分别保留通知；源码仓库许可不自动覆盖 SDK、权重或生成资产。[上游第三方说明](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/THIRD_PARTY.md)。

## 3. 分批实施与验收

下面的工具路径是建议新增项，除已引用的 H 工具外均尚未实现。每批只完成一个行为；代码、合同及测试交 Astra medium 审实际 diff，修复后复核。每批一份短记录加 STATUS，不生成成套重复文档。

### P1：可重建的 Windows 环境入口

- 产物：`tools/host/` 下的环境预检/初始化入口及简短说明；接受显式 Python executable 路径，验证版本、AMD64/ARM64 和 pip，使用仓库 `.venv`。
- 范围：基线环境仍按现有 requirements；不自动覆盖现有 venv。QAIRT 环境单独放在忽略的 `local/venvs/qairt-<version>/`，版本由 P3 决定；系统 Python 3.9 保留。
- 验收：新空目标环境可由 Python 3.10+ 创建并跑主机 suite；3.9、失效路径、有冲突的现存环境报明确错误；含空格路径可用。记录基础解释器来源及重建命令，不依赖 `py -3` 或 Codex 缓存固定路径。
- 依赖：无 SDK/FSR 依赖。下一个首先执行的批次。

### P2：外部资产登记与只读核验

- 产物：`tools/assets/` 中的小型登记/核验工具、合成 fixture。记录组件、来源 URL、版本/commit、许可通知位置、平台/架构、实际文件 SHA-256、用途及缺失原因。
- 范围：仅检查调用方明确提供的根目录；私有绝对路径留本地，公开记录使用逻辑名/相对路径。真实资产登记与 H2 synthetic schema 分离，不把 H2 的安全标志改成可用于生产。
- 验收：完备合成包通过；缺文件、哈希不符、错误格式、路径越界和过大输入确定性拒绝；无实际文件时不得填造哈希。区分文件 present、元数据 verified 与执行 not_run。
- 依赖：P1；工具测试不需要任何外部资产。

### P3：QAIRT 获取、隔离安装与工具冒烟

- 产物：一套可追溯的本地 SDK、专用 Python 环境及工具能力表；版本选择优先核查上游 2.50，不可用/不匹配时记录原因再选择候选，不默默混装 2.45/2.50。
- 范围：先核对下载来源、许可和包内主机支持；只运行适合本机架构的版本/help 检查。SDK 路径和 PATH/PYTHONPATH 仅注入本次子进程。只有实际需要编译时才准备相应 C++ 工具链。
- 验收：可运行的 converter、quantizer、metadata 工具分别记录精确 argv、版本、退出码；缺工具、错误 Python/架构给出明确诊断。Windows CPU backend 和离线 HTP prepare 各自登记支持证据，未支持者列为后置，不能因 help 成功写成转换成功。
- 依赖：P1/P2 和合法 SDK 下载。账户登录/条款需要本人操作时，仅暂停本批资产步骤，转做 P5/P9；不能把安装说明当作安装完成。

### P4：目标库的离线 ABI 清单

- 产物：Windows 可运行的只读 PE/ELF 检查器与自有最小 fixture，登记 machine、位数、可读取的 ELF interpreter/NEEDED/GLIBC 符号版本和 SDK 版本归属。
- 验收：拒绝截断/越界结构，区分 Windows PE、Android 候选、Linux glibc 候选；不能仅凭 AArch64 或文件夹名认定 ABI。合成样例覆盖缺失字段和错误架构；取得真实 SDK 后生成候选清单，设备匹配结论仍 unknown。
- 依赖：P2；真实库登记追加依赖 P3，解析器本身不依赖 SDK。不在 Windows 加载 ARM64 ELF。
- 可先交付合成解析部分，但 P4 保持 `in_progress`；真实 SDK 清单条件不满足时记录 `blocked`。仅在解析测试和可取得候选库清单均完成、缺失目标库如实登记后标记 P4 complete，平台兼容性仍 unknown。

### P5：自有小图与 CPU 数值基准

- 产物：小型 Conv/Add/ReLU ONNX 图和独立参考输出，包含零输入、固定图案及固定种子非零输入；锁定 ONNX/CPU runtime 组合。
- 验收：ONNX checker、固定 tensor 名/shape/dtype、CPU backend 身份与逐元素对照通过；改变输入必须影响指定输出；事先规定容差，测试错误 shape 与异常数值。图不能被全常量折叠；依赖和张量大小保持小型。
- 依赖：P1/P2；无需 FSR 或 QNN。环境放在独立的 `local/venvs/reference/`，不污染基线 `.venv`。

### P6：小图的 QAIRT 转换与量化

- 产物：将 P5 小图转换/量化为所选 SDK 支持的中间表示，读取真实 graph/tensor/encoding 元数据，登记生成链及哈希。
- 验收：实际转换成功、产物可被配套 metadata 工具读取；校准列表和量化 convention 可追溯；失败保留日志、不发布半成品为成功。若该 Windows 包支持 CPU 执行，则与 P5 比较并注明 backend；否则仅报告 build，CPU SDK 执行保持 not_run。
- 依赖：P3/P5。HTP context 只在本版 Windows 工具明确支持时作为另行选择的实验；Linux-only prepare 不阻塞本批中间表示验收。小图不命名为 FSR。

### P7：FSR v07 材料接收与权重提取

- 产物：锁定研究源码和合法模型材料；封装/参数化原有提取流程，将结果写到新的 `artifacts/` 子目录，记录来源、许可和 SHA-256。
- 验收：实际五类输入齐备、上游自检和 provider 交叉核对通过；解析失败不得把输出标成有效；对自有片段补截断、错误版本和字节序测试。生成 npz/graph spec 不随源码发布。
- 依赖：P2 和可核验的 AMD 源材料；不依赖 QNN。若只有官方签名 DLL 或材料来源无法核验，本批为 blocked，其它资产无关批次继续。不得用不明 `.bin`、镜像压缩包或 XLSR 顶替。

### P8：FSR 网络子图的 CPU 对照

- 产物：基于 P7 真实提取结果运行上游 simulator/ONNX 参考，选可支持的小尺寸或有限样本，登记图、权重、输入与分阶段输出。
- 验收：记录自检与独立算子/不同实现的交叉对照，明确两者共享来源时的证据局限；包括量化、布局和非零输入，容差预先定义。只散列输出不算数值正确。上游只支持固定大尺寸时先评估内存，不凭空 reshape。
- 依赖：P7/P5。缺官方 golden 则官方等价性 unknown；此批只覆盖选定网络分区，GPU 特征准备、重建和真实时序输入未验证。完整模型 QNN 转换另批规划，不塞入本批。

### P9：生命周期加固（明确分三个单次批次）

- P9a 资源预算/背压：为 H4 的旧代隔离资源规定数量与容量上限，明确其如何计入同 context 在途限制。验收：连续 submit/reset/timeout 达到上限后拒绝新工作；仍在途对象不被淘汰；匹配完成后回收、解除背压；拒绝路径不改 generation/history。依赖 H4。
- P9b 幂等记录保留：为消费确认和 reset 去重记录确定保留范围及过期通知语义。验收：记录数量有界；保留窗口内重试幂等，冲突通知拒绝；过期重复通知不能二次提交或推进 generation。依赖 P9a，单独审阅记录过期与公共幂等语义的兼容性。
- P9c 合成失败/关闭：增加最小 execution-failure/close 事件和可区分的候选 history 测试。验收：处理中失败与关闭不提交候选；仍在途资源继续保留，显式完成后才回收；迟到事件不能污染新代。永久不完成明确保持隔离/阻塞，不能宣称已取消。依赖 P9a/P9b，不扩到逐 GPU 阶段实现。

三批均不依赖 SDK/FSR。策略若改变共享合同，配套更新并由 Astra 审阅；仍不实现网络 daemon 或真实后端。P1–P8 加 P9a/P9b/P9c 共 11 个单次执行批次。

## 4. 执行顺序与停止条件

默认先 P1 → P2 → P3。P3 被账户/下载/平台条件阻塞时，继续 P5 或 P9；P4 的合成解析测试也可继续。P6 需要 P3+P5；P7 需要独立满足 FSR 资产条件，P8 需要 P7+P5。这些分支只按独立文件边界派工，不为并行而重复研究。

每次单次提示只取一批（P9 必须选一个子批次）并停止；这一轮仅完成评估和队列规划。P 项 complete 不改变 M0–M9 的设备门槛。全部必需验收通过才结束本阶段；剩余项均有具体外部阻塞时结束本次执行，保留阶段未完成和对应 blocked 项，不自动扩到驱动、网络服务、NGX、Decky、Steam 安装器或游戏验证。

有设备后再决定 Linux runtime、FastRPC/BSP、HTP 架构及真正的执行链。没有设备时仍可显著减少来源、工具版本、文件格式、图构建和状态机的不确定性；不能据此估计 HTP 性能或整帧收益。
