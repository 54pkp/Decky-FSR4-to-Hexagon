# Windows 无设备活动计划

更新日期：2026-09-22。此页只列 **Windows、未连接 Odin 3** 时可独立验收的新工作；H1–H4、P1–P8 与 P9a–P9c 的完成范围已移至[已完成主机批次](COMPLETED_HOST_BATCHES.md)。当前状态和唯一进度表以 [STATUS](../STATUS.md) 为准，本轮规划记录见[文档路线刷新](../validation/host/2026-09-22-documentation-roadmap-refresh.md)。本页只定义 ID、依赖、验收和证据边界，不复制实时状态；所有叶子项在 STATUS 中默认 `not_started`，开始后才由协调者增加逐 ID 覆盖。

设备建档、Linux/Armada、真实 QNN/HTP 执行、游戏、画质、性能、功耗及 POSIX 对抗验证均属于[设备执行计划](DEVICE_EXECUTION.md)，不在本页验收。这里的 `complete` 最多证明指定 Windows 主机行为；不得外推为 FSR4 等价、目标 ABI 可用、HTP 成功或产品可用。

## 执行规则

- 每次只选一个 ID（带 `a/b` 的子批也各算一次），满足依赖后实现、测试、记录，再由协调者更新 STATUS；不要把整条分支塞进一批。
- 默认先清 R01–R05 的已复现缺陷，再做与其不冲突的 R 项。F、E 是可排期分支，不是本轮已启动工作，也不要求为了等待资产或设备而停止其它独立批次。
- 真实外部资产必须绑定来源、版本、哈希和实际环境；旧收据、自洽收据或 ignored 目录名本身不是来源证明。SDK、模型及大产物继续留在忽略目录。
- 测试中的 `skipped`、缺依赖和 `not_run` 分别汇总，不能算 pass。历史验证报告保持原样；新批次只写一份短记录。
- Windows 离线 HTP prepare 只做可行性实验。工具存在、命令成功、prepare 可调用乃至生成文件，都不能代替目标设备加载和 HTP 执行；实验失败也应保留具体 SDK/算子限制，而不是承诺一定生成成功。

## R：审计修复与可复现入口

R 分支关闭 2026-09-22 审计在无设备环境中可复现或可固化的欠账。前三项固定为最高优先级。P7现有五输入与提取器的固定哈希核验不重做；新项只补环境收据和P8消费端信任链。上游材料不是独立Git checkout，不能用向上命中的本仓库commit冒充来源。

| ID | 小批次与主机验收 | 依赖 | 不证明 |
| --- | --- | --- | --- |
| R01 | 修复 P5 导出失败清理的目录所有权：只有成功独占创建者可清理；竞争注入中另一创建者的目录和哨兵保留，串行成功/失败回归通过 | 无 | ONNX 模型正确性或 FSR |
| R02 | 修复 P6 发布竞争：每次使用私有唯一 staging，只删除本次创建对象；双发布者竞争中赢家及其文件不被败者删除，失败不发布 success receipt | 无；可复用 R01 的所有权约定 | QAIRT 转换或 HTP 正确性 |
| R03 | 严格解析 P6 encoding：拒绝非整数/错误类型 bitwidth 与非允许布尔表示，保留合法 SDK 元数据回归；不得以截断或 truthiness 静默正规化 | 无 | 当前 SDK 输出有错或真实 FSR encoding 可用 |
| R04 | 关闭 M0 evidence 检查到打开的 TOCTOU：基于实际打开对象验证边界/类型并读取；路径替换注入不得读到根外内容，既有 fixture 仍通过 | 无 | Linux `/proc`、sysfs、权限或设备采集 |
| R05 | 将 M0 公开脱敏发布改为整体事务：唯一 staging、完整校验后一次发布、失败回滚；第二文件写失败不得留下可被误取的半成品 | R04 | 已发生隐私泄漏；也不替代设备端脱敏验证 |
| R06a | 固化 QAIRT/P6 前端重建配方：Python、33 项 QAIRT 基线依赖及新增 ONNX/protobuf 精确可校验，空 venv 重建后专测与 `pip check` 通过 | P3 历史资产仍可用 | 所有 SDK/native 依赖闭包或设备兼容 |
| R06b | 将 P6 执行 SDK 绑定到固定快照或等价文件闭包；执行前验证实际导入模块与 native 候选，任一绑定文件被替换时拒绝 | R06a | 密封供应链、恶意主机防护或 HTP |
| R06c | 补全 P6 环境 receipt：记录并校验实际 Python 版本/解释器哈希、包清单与 P3 快照身份；环境漂移时拒绝 | R06a–R06b | SDK 文件闭包之外的系统依赖均已密封 |
| R06d | 规范 P6 输出父目录诊断：缺直接父目录时返回统一 PipelineError/稳定退出码，而不是裸 `FileNotFoundError` traceback；正常路径不变 | 无 | 转换产物正确或任意 I/O 故障均可恢复 |
| R07 | 把 Windows symlink 无条件 skip 改为能力探测：可创建时实跑，不可创建时记录可复现原因；两种分支都有测试 | 无 | POSIX symlink/hardlink 竞态；这些留设备计划 |
| R08a | 建立显式多 venv 验证入口：依次运行 baseline、reference、fsr-extract、QAIRT suite，保留每组解释器/环境、pass/fail/skip/not_run 和总退出码 | R06a、R07 | CI 云环境、Linux 或设备结果 |
| R08b | 固化 P3 后代进程继承 stdout/stderr 导致超时回收延长的回归；验收入口在预算内返回、诊断子孙状态且不误报工具成功 | 无 | POSIX 进程组/SIGALRM 或任意第三方进程可强制终止 |
| R08c | 增加不依赖私有 SDK/资产的公共 CI 工作流，Windows覆盖最低支持Python与当前锁定版本的可公开重建suite，准确报告能力skip；未跑的ARM64/Linux组合仍not_run，私有多venv入口由R08a单独运行 | R07、R08a | QAIRT/FSR私有资产、所有架构/平台或设备CI已覆盖 |
| R09 | 补 P7 独立语义负例：graph marker/count，以及公共 NPZ 的 100-array、shape、dtype 约束逐项畸形拒绝；不只覆盖坏 ZIP | P7 历史 fixture | 完整图语义、官方 golden 或运行等价 |
| R10a | 补全 P7 环境 receipt：绑定真实 Python/NumPy、完整 argv 与 extractor stdout gate；缺项或环境摘要不符时拒绝 accepted 发布 | R09 | 来源真实性、完整可重复执行或官方等价 |
| R10b | 固化 P8 对 P7 的信任链：消费者校验已知 accepted receipt 摘要及其来源/输出绑定，不接受仅内部自洽或旧 wrapper/validated receipt | R10a | 重新提取来源材料或官方等价 |
| R11 | 将 P9a 历史附加检查固化为测试：8 类 retained 状态、错误身份、大整数容量、active+isolated 边界和永久在途背压 | 无 | 实际 RAM/VRAM/DSP 峰值或后端取消 |
| R12a | 将 P9b 历史压力检查固化：消费/reset 并发、25+ 窗口和 namespace 独立；明确淘汰后与跨重启仍不保证幂等 | R11 | 稳定 wire 错误或持久幂等 |
| R12b | 将 P9c 历史压力检查固化：五类 retained、四代预算及 close/completion 并发，迟到事件不污染新代 | R11、R12a | 真后端静止、安全销毁或永久卡死恢复 |
| R13 | 建当前 artifact 索引：区分 accepted/current、历史/过时和审计临时收据；消费者按固定索引与摘要选取，旧 P8 1-LSB receipt 不得被误认当前 0-LSB 证据 | R10b | 重新执行资产来源核验或产物正确性 |

## F：真实 FSR 离线分支

F 分支从已有 P7 真材料继续，但仍是 CPU/ONNX/QAIRT 的离线实验。每一步遇到算子、内存、SDK 或来源限制时，记录为该批的具体结果，不用 toy graph、XLSR 或同源输出替代。

| ID | 小批次与主机验收 | 依赖 | 不证明 |
| --- | --- | --- | --- |
| F01 | 固化 pass1–13 CPU 参考清单与合同：为每 pass 登记算子、权重、tensor、shape/layout、量化约定、固定输入和独立预期来源；缺项保持 unknown | R10b、P7 历史资产 | 任一 pass 已实现、完整 FSR 或官方等价 |
| F02a | 实现并验收 pass1–4 CPU 参考与逐层独立对照，覆盖非零输入、signedness、饱和及预声明容差 | F01 | pass5–13、官方 golden 或实时性能 |
| F02b | 实现并验收 pass5–9 CPU 参考与逐层独立对照，沿用 F01 边界且不由被测实现生成唯一预期 | F01、F02a | pass10–13、GPU 前后处理或时序 |
| F02c | 实现并验收 pass10–13 CPU 参考与逐层独立对照；若真实算子边界要求调整分组，开工前在记录中固定，但所有 pass 必须恰好归属一个 ID | F01、F02b | 官方等价、GPU 重建或设备执行 |
| F03 | 组装 pass1–13 完整 CPU 主图，并以独立分段结果做端到端/逐层交叉检查，首个偏差可定位且容差预声明 | F02a–F02c | pass0、GPU 前后处理、完整 temporal FSR 或性能 |
| F04a | 导出一个最小连续真实分段 ONNX，固定 tensor 名/shape/dtype/QDQ 与来源摘要；checker 通过并拒绝不支持的动态改形 | F02a、R03 | 完整 ONNX 或 QAIRT 可转换 |
| F04b | 组装 pass1–13 完整 ONNX，逐项核对 F01 图清单、权重和输入输出，不以单段成功替代完整 checker | F03、F04a | ORT 数值正确、QAIRT 或 HTP 可用 |
| F04c | 用独立 ONNX Runtime 对 F04b 做逐 tensor 对照，定位首个误差点并与 F03 完整 CPU 主图比较 | F03、F04b | GPU 前后处理、时序或官方 golden |
| F05 | 建真实 FSR calibration/encoding 检查：明确权重/激活 signedness、粒度、scale/offset、I/O dtype 与数据集身份，畸形或不完整合同拒绝 | F03、R03 | 数据集代表真实游戏或量化质量达标 |
| F06a | 将 F04a 最小真实分段做 QAIRT float 转换并读取 graph/tensor metadata；转换与结构验收成功才可 complete，不支持则记录具体 blocker | F04a、R06b–R06c | 完整 FSR DLC、W8A8 或 HTP |
| F06b | 对 F06a 分段做 W8A8/B32 量化，逐项核对 F05 encoding 与中间 tensor；量化/metadata gate 成功才可 complete | F05、F06a | 完整网络量化质量或目标 v79 可用 |
| F06c | 仅在能力探测确认支持时，用 QNN CPU 实跑 F06b 并与 F04c 对应分段比较；不支持则保持未完成/阻塞，不把探测记成执行通过 | F04c、F06b | HTP、完整网络或设备性能 |
| F07 | 调查 Windows 离线 HTP prepare 对 F06b 分段的可行性，分别记录“调查完成”和“context 生成 gate”；调查可在 gate 失败时完成，但只有真实生成才标记 `generated=true` | F06b | context **保证生成成功**；更不证明设备可加载/执行 |
| F08a | 建非 production 的真实模型 manifest，关联 F03/F04/F05 已验收图、权重、encoding 和来源；SoC/context/shader 等未知字段保持 unknown | F04c、F05、R13 | production-ready manifest 或 HTP 可用 |
| F08b | 建小型序列回放合同与 fixture，固定帧身份、阶段输入输出、reset/history 边界及缺失 temporal 输入；只验证离线数据链 | F08a | 完整 temporal FSR、真实游戏帧或画质结论 |

## E：协议与主机工程准备

E 分支只构建自有 fixture、测试 host 和离线事务/观测部件。它不连接真实游戏，也不冻结未经设备证明的最终 ABI。

| ID | 小批次与主机验收 | 依赖 | 不证明 |
| --- | --- | --- | --- |
| E01 | 实现最小版本化 wire codec：长度、stride、容量、整数溢出、半包、未知版本和稳定错误分类的 round-trip/负例测试 | H4 历史合同 | 最终跨进程协议、鉴权或网络安全 |
| E02 | 在自有双端 mock 中验证六元身份、单 context 单在途、reset、断连及 `result_consumed` 后才提交 history | E01、P9 历史行为 | socket 发送即游戏写回、真实后端取消或 M4 完成 |
| E03 | 建最小自有 Windows PE 导出库，只实现测试 ABI 的 create/evaluate/destroy 可观察骨架；导出表和错误输入由自有 host 验证 | 无 | NGX/DLSS 兼容或任何游戏可加载 |
| E04 | 建独立 PE 测试 host，覆盖参数对象生命周期、重复创建/销毁、版本/能力拒绝及崩溃隔离，不接 Steam/Proton | E03 | 真实游戏调用约定、FEX/Wine/Proton 链 |
| E05 | 建自有 D3D11 纹理 fixture，逐项测试 format/view/mip/RowPitch、readback/writeback、context ownership 和资源状态恢复 | E04 | 真实游戏资源语义、D3D12/Vulkan 或零复制 |
| E06a | 在临时目录实现只读部署 `plan`：生成目标、前置条件、原文件哈希和预期变更；外部修改或路径越界在 apply 前拒绝 | 无 | 实际安装、Linux 用户服务或可发布产品 |
| E06b | 实现事务 `apply/restore`：唯一 staging、哈希备份和 journal；正常应用后可按同一 journal 精确恢复，重复请求幂等 | E06a | 崩溃恢复、Steam/Decky 安装或运行中会话安全 |
| E06c | 实现 `recover` 故障注入：在各提交点中断后可判定前滚/回滚，外部修改冲突不覆盖用户内容 | E06b | 断电文件系统语义、Linux 服务或卸载全链 |
| E07 | 定义 trace/event schema 与主机记录器：阶段、fresh/repeat、身份、clock domain、错误和丢事件显式；不同钟域不得直接相减 | E01–E02 | 设备时钟相关性、input-to-photon、FPS/功耗收益 |
| E08 | 组装仅自有资产的离线 integration host：PE 调用、D3D11 fixture、wire mock 和 trace 以显式边界串联；故障注入证明不提交错误 history | E02、E04–E05、E07；可选 E06 | 完整产品、真实 FSR/HTP、游戏画质/性能或部署可用 |

## 设备分界与停止条件

无设备批次不得吸收以下验收：Odin 3 真实 M0 档案、Linux glibc/Android bionic/Hexagon 库装载、FastRPC/CDSP/固件/权限、普通用户 HTP、真实 GPU 同步、游戏 Evaluate/写回、长序列画质、帧率/延迟/温度/功耗。P4 留下的 POSIX 目录到 hardlink 竞态以及普通 symlink、进程组、SIGALRM、真实 sysfs/权限也只在相应 Linux/设备环境验证。

可并行推进的主线是 R 清账、F 离线模型和 E 主机工程；真正产品关键路径仍在设备计划中汇合。某一分支缺资产时只暂停该分支；若一个批次的验收会要求真实设备或改变最终 ABI，则停止该批，把问题和最小所需输入写回 STATUS，而不是用 mock 宣告完成。
