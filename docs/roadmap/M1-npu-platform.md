# M1：Linux QNN / Hexagon NPU 平台闸门

状态：**未执行；没有 Odin 3 HTP 成功记录。** 前置：[M0 设备建档](M0-device-baseline.md)；后续：[M2 FSR4 v79 离线移植](M2-fsr4-port.md)。本节点不需要先确定游戏。

执行约束和状态字段遵循 [AI 实施总则](../ai/IMPLEMENTATION_GUIDE.md)、[共享合同](../architecture/CONTRACTS.md)、[项目状态](../STATUS.md)。唯一的核心结论是：**普通用户能否在目标 Linux 上运行已知小图，并证明运算确实发生在 HTP。**

## 1. 目标和非目标

交付一个最小原生 AArch64 Linux QNN 探针、一套具有已知答案的小图、可追溯运行日志和错误分类。把内核/固件、FastRPC、Linux ABI、QNN provider、context 和执行分层诊断。

非目标：不运行 FSR4，不接 Steam/DLL/Decky，不追求零复制，不自动调频，不修改 fuse/设备树/内核，不把 root 推理作为正常运行方式。CPU backend 可以辅助参考比较，但必须明确命名，不能自动回退后仍返回“HTP 通过”。

## 2. 前置材料和无设备工作的边界

| 材料 | 要求 |
| --- | --- |
| M0 档案 | `device_profile_id`，镜像/内核/libc/remoteproc/设备节点实际记录 |
| SDK | 使用者自行取得的 QAIRT/QNN，版本、取得方式、适用条款和本地路径 |
| Linux host 库 | 原生 AArch64、与 glibc/加载器匹配的 backend/system/stub 及依赖 |
| DSP 库 | 与 SDK、HTP 架构及平台匹配的 skel；不能只根据文件名判断可用 |
| FastRPC 用户态 | 库版本、来源、设备节点和普通用户权限；平台需要的 PD/listener 材料 |
| 小图 | 自行生成、无第三方模型权重、确定性输入和参考计算 |
| 开发主机 | 固定编译器/CMake、所需 SDK headers；不提交 proprietary SDK 文件 |

无设备时允许构建探针、测试错误处理、生成可审计小图和离线 context、在明确标记的 CPU backend 验证参考输出。这些最多是 `build` / `host_test`，M1 的 `device_test` 必须保持 `not_run`。

没有匹配的 Linux QNN runtime 时，先把问题写成平台依赖阻塞。Android bionic `.so` 和 Windows ARM64 DLL 不能直接替代 Armada 的 Linux glibc 库。SDK 中 AArch64 OpenEmbedded/glibc runtime 可以作为候选，但必须核对实际 ISA、加载器、符号版本、依赖与 BSP/FastRPC 组合；既不能假定兼容，也不能仅凭 OpenEmbedded 标签认定不兼容。

## 3. 源码阅读与可复用边界

1. [hexscale fork 的真实 QNN runtime](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/daemon/src/qnn_runtime.cpp)：重点读 provider/version 查询、`contextCreateFromBinary`、`graphRetrieve`、`graphExecute` 和清理顺序，可参考 RAII 与错误处理。
2. [fork 探针](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/tests/qnn_probe.cpp)：有真实执行、输出比较和错误输入检测；常量输入/均值并不足以构成本节点完整验收，需要不同输入及实际 HTP 证据。
3. [fork README-QNN](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/README-QNN.md) 与 [已有验证报告](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/docs/validation/0.2.0-dev1.json)：确认哪些是 Windows CPU/Vulkan、离线生成和交叉编译，不能继承为 Odin 3 成功。
4. [XLSR v79 清单](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/models/xlsr-sm8750-v79.json)：`socModel=69`、`dspArch=79` 只供查所选 SDK 的枚举，不把它当设备读数或 FSR4 模型。
5. [Android fsr4 QNN 初始化](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/qnn_service.c#L576) 与 [构建脚本](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/build.sh)：用来识别需要替换的 Android 分配/链接假设，不作为 Linux 安装脚本运行。
6. [RP6 研究边界](https://github.com/puzzled-pancake/rp6-npu-unlock/blob/31c701d8b0a95cde4398b6af6929cdcf75eb83e8/docs/RESEARCH_NOTES.md)：只学习分层定位；不移植其中模块补丁和刷写流程。

Linux FastRPC 的动态 PD 与某些 static-PD daemon 是不同层次；不要把“存在名为 cdsprpcd 的进程”写成所有 Linux 系统的通用通过条件。以匹配平台的驱动/用户态源码和所选 SDK 文档为准，并将新增资料固定到 commit 或版本。

## 4. 建议模块和接口（尚未实现）

| 拟议路径 | 职责 |
| --- | --- |
| `tools/qnn-probe/main.cpp` | 解析明确参数、运行阶段、写结构化结果 |
| `tools/qnn-probe/tiny_graph/` | 生成简单量化图、固定随机种子、参考输入/输出 |
| `runtime/qnn/backend_loader.*` | 受控路径加载、provider/API 版本校验 |
| `runtime/qnn/context.*` | context 生命周期、graph/tensor 元数据 |
| `runtime/qnn/buffer.*` | 先实现 SDK 支持的普通 client buffer，再独立试验注册内存 |
| `runtime/qnn/error.*` | 阶段、errno、QNN code、可读解释；不抹去原始码 |
| `docs/validation/M1/YYYY-MM-DD-<work-package>.md` | 实际运行时创建的公开结果摘要与证据索引 |

建议 C++20 + CMake；若所选 SDK/toolchain 需要 C++17，通过 ADR 记录调整。动态加载 proprietary runtime，以隔离可选 SDK 依赖并给出缺失库错误；头文件版本仍必须锁定，动态加载不是 ABI 兼容保证。native 进程放在 host 用户会话，与实际 Steam 容器/rootfs 的 ABI 边界分开核对。

状态机建议为 `uninitialized → libraries_loaded → backend_ready → context_loaded → executing → ready → closed`；任一步失败进入带阶段信息的错误状态并释放已取得资源。创建/销毁次数、输入校验失败和执行失败分别计数。

超时不能当成后端工作已取消。`graphExecute` 未返回时不得释放或复用 context/buffer/library；先停止新请求，按已验证的后端能力等待或隔离探针进程，并记录是否需要外部恢复。SDK 没有支持的取消机制时，不编造 `cancel` 成功。

## 5. 分批实现与输出

### M1-A：依赖清单和 ABI 检查

1. 固定一套 SDK 版本，记录 headers、host libs、DSP libs、转换器版本；不要混用上游 QAIRT 2.50 与 fork 的 2.45 文件后假定兼容。
2. 检查 ELF machine、interpreter/依赖、最低 GLIBC 需求，保存哈希；检查 SDK 内可用的 Linux 目标，不从 Android 路径照抄。
3. 读取设备权限与组，检查 remoteproc 的真实状态，记录固件和 FastRPC 版本。
4. 对每个不匹配项给出具体阻塞：`host_abi_mismatch`、`missing_runtime`、`permission_denied`、`missing_dsp_dependency` 等。

输出：环境兼容矩阵和原始证据。只读检查通过不等于可执行推理。

### M1-B：provider、context 和元数据探针

1. 从显式路径加载 backend/system 库，解析 SDK 要求的 provider 入口，校验接口版本和必需函数指针。
2. 记录实际 backend ID、库绝对路径、哈希及 provider 版本；请求 HTP 时拒绝 CPU 库。
3. 加载小图 context 并读取 graph/tensor 元数据，检查数量、名称、shape、dtype、量化定义和字节上限。
4. 完成逆序释放，验证加载失败后重试不会保留半初始化对象或返回前次结果。

输出：可以区分“加载库”“打开后端”“载入图”的工具。context 能加载仅是中间阶段。

### M1-C：已知小图真实 HTP 执行

1. 使用含小型 Conv/Add/ReLU 等目标后端支持算子的确定性图；图不能完全由常量折叠消除，也不能只测试空图。
2. 使用至少三种不同输入（零、固定图案、带固定种子的非零数据），事先计算参考输出和量化容差。
3. 显式调用 `graphExecute`，保存 QNN 返回码、每次 input/output digest、耗时与可获得的 HTP profiling。
4. 与各输入的参考答案逐项比较，拒绝非预期的全零、恒定或旧输出、错误张量长度和不符合容差的结果。零输入或 ReLU 合法产生全零时按参考答案判定，不能仅凭“输出全零”报失败。
5. 记录 profiler 能提供的实际设备执行事件；若当前 runtime 不支持足够 profiling，补充 SDK 设备日志/执行证据并说明限制，不能只把库名当证据。

输出：小图生成输入、模型/脚本哈希、参考答案、真实设备输出、明确的 backend 证明链。CPU 对照另存报告。

### M1-D：生命周期和失败恢复

1. 连续运行至少 1,000 次，统计 p50/p95/p99、错误数、进程 RSS 和可观测 DSP 资源；该次数是拟议基础门槛，不是性能承诺。
2. 完成至少 10 次正常进程启动/执行/退出，检查句柄和内存没有随次数持续增长。
3. 注入路径不存在、错误模型哈希、不支持的版本、错误 tensor 大小，确保执行前拒绝且不输出旧结果。
4. 在可控样例进程中测一次运行时中止与重新启动；不向系统 DSP 发 reset，不故意提交可破坏内存的无效指针。
5. 首次系统启动后的验证与后续启动复验分开记录。挂起/恢复和图形并发作为附加稳定性检查，只有设备所有者安排的操作才执行，程序不自动重启机器。

输出：稳定性报告、失败分类、是否需要进程重启或系统协助恢复。若发生 DSP crash，保留日志并停止压力循环。

### M1-E：闸门审阅

核对普通用户权限、真实 HTP 证据、数值结果和生命周期报告。给 M2 输出锁定的 SDK/SoC/HTP/库组合，不输出“任意骁龙都支持”的结论。发现 firmware/ABI 问题时，将平台修复拆为独立 ADR；探针不悄悄变成系统安装器。

## 6. 拟议报告接口

仅为 JSON 示例，**没有进行真实测试**；字段以共享合同为准。

```json
{
  "schema_version": "draft-0",
  "example_only": true,
  "device_profile_id": "example-odin3-baseline",
  "model_manifest_id": "example-tinygraph-v79",
  "evidence_level": "device_test",
  "gate": "not_run",
  "backend_requested": "htp",
  "backend_observed": null,
  "qairt_version": null,
  "soc_model_enum": null,
  "htp_arch_observed": null,
  "graph_execute_count": "0",
  "output_validation": {"comparison": null, "max_abs_error": null},
  "profiling_evidence": [],
  "failure": null
}
```

失败对象至少包含 `stage`、稳定错误类别、原始 QNN code/errno、依赖文件摘要和是否可重试。不得在报告中记录许可证令牌或向公开仓库拷贝 SDK 二进制。没有执行的时延写 `null`，不是 `0 ms`。

## 7. 现有只读命令与未来命令

以下 Bash 命令只检查已存在的库和文件。先将 `QNN_HOST_LIB` 设置为 M1-A 确认的某个本地 Linux host 库路径；示例不猜测设备安装位置。

```bash
QNN_HOST_LIB='/absolute/path/to/verified-linux-host-backend.so'
file "$QNN_HOST_LIB"
readelf -h "$QNN_HOST_LIB"
readelf -d "$QNN_HOST_LIB"
readelf --version-info "$QNN_HOST_LIB"
sha256sum "$QNN_HOST_LIB"
id
ls -l /dev/fastrpc* /dev/dma_heap/* 2>/dev/null
if command -v ldconfig >/dev/null 2>&1; then ldconfig -p; fi
```

不使用 `ldd <来源不明的可执行文件>` 作为静态审计方法。`readelf` 的结果仍需与 host libc 对照，不能直接推导 `dlopen` 成功。

下面是 **拟议 CLI，当前不存在**，必须在实现帮助文本、输入合同和本机 dry-run 后才使用；执行模式会初始化 NPU，并非只读采集：

```text
fsr4hex-qnn-probe inspect --runtime-dir <linux-runtime> --context <tiny.bin>
fsr4hex-qnn-probe execute --backend htp --manifest <tiny-manifest.json> --inputs <bank> --report <new-report.json>
fsr4hex-qnn-probe repeat --backend htp --manifest <tiny-manifest.json> --iterations 1000 --report <new-report.json>
```

QAIRT 自带工具的命令/库名称随锁定版本而定。先保存该版本 `--help` 和官方示例，再编写可执行命令；不能将文档里的占位参数当作已跑过的命令。

## 8. 分层验证矩阵

| 层级 | 内容 | 可通过的项目 | 仍不能声明 |
| --- | --- | --- | --- |
| `source_review` | loader、FastRPC、SDK API 审阅 | 初始化和依赖路径明确 | 设备可用 |
| `build` | native/cross AArch64 ELF 和链接审计 | 编译产物/ABI 目标明确 | HTP 图已运行 |
| `host_test` | fake backend、错误注入、CPU 对照 | 错误处理/数值参考可信 | NPU 性能/兼容性 |
| `device_test` | 小图 HTP 实际执行、输出与 profiling | 本组合的 M1 平台门槛 | FSR4 或游戏可用 |
| `game_test` | 本节点不要求 | 仅记录并发观察，若有 | 代理接入或整帧收益 |

fake backend 必须使用独立测试路径和明显名称，生产 `--backend htp` 不得加载它。所有生成的空文件、placeholder context 和“模拟成功”均不能进入实际设备 gate。

## 9. 通过门槛和暂停点

通过必须同时满足：目标设备普通用户执行；匹配且可追溯的 Linux runtime；真实 HTP graphExecute 证据；至少三种输入数值对照；连续执行与进程生命周期无未解释错误；报告引用有效 `device_profile_id` 和小图 manifest。性能只报告测量，不以某个上游毫秒数作为硬门槛。

以下情况暂停相关执行：架构/SDK/固件不匹配、HTP 身份无法证明、输出不随输入变化、DSP crash、内存增长未解释、必须 root 才能推理且权限方案未解决。允许继续分析日志、完善测试与 M2 离线模型准备，不能把 M1 标为通过。

错误定位顺序：文件/ABI → provider/API → backend/device → context/graph → tensor/buffer → execute → 数值验证。FastRPC 节点缺失不是“熔断”的直接证据；存在节点也不是成功证据。

交接按 [模板](../templates/handoff.md) 保存 SDK 精确版本、依赖哈希与路径角色、SoC 枚举出处、HTP 实际身份、最小复现命令、日志、重复次数、恢复要求和未验证项。报告旁保存对应 `-handoff.md`，原始证据在 `artifacts/M1/<run-id>/`，实际执行时才创建。M2 只能继承这一**完整组合**，升级任一平台依赖需重测相应门槛。

## 10. 可复制给下一位 AI 的任务提示词

> 请按本文件实现 M1 的最小 Linux QNN 探针，先读共享合同、状态与 M0 设备档案。先完成依赖/ABI 审计，然后分批实现 provider、context、确定性小图 graphExecute、输出比较和生命周期测试。只用普通用户、原生 AArch64 Linux runtime；CPU/fake backend 必须独立标记，禁止失败后静默回退。不要刷机、修改设备树、运行 RP6 解锁流程或分发 proprietary SDK。不要仅因编译成功、provider 可加载、context 可创建就宣布通过。没有设备时交付工具、明确的离线构建证据和待执行命令，device_test 保持 not_run。真实 HTP 执行需保存后端身份、返回码、输入/输出摘要、数值误差与 profiling/设备证据。遇到 DSP crash 停止压力测试。最终列出 M2 能继承的精确环境组合和所有未验证项。
