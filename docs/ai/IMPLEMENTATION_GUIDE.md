# 证据速查与接续指南

[文档地图](../README.md) · [STATUS](../STATUS.md) · [协作流程](MULTI_AGENT_WORKFLOW.md)

## 先判断你在查什么

- 做下一批：STATUS → [无设备计划](../roadmap/HOST_PREPARATION.md)或[设备计划](../roadmap/DEVICE_EXECUTION.md)中的具体 ID → 相关源码/测试。
- 找已完成内容：[H/P 历史索引](../roadmap/COMPLETED_HOST_BATCHES.md) → 对应日期记录。历史 complete 不表示新审计问题已修复。
- 跑现有工具：对应 `tools/**/README.md`，使用明确环境；不要直接把 roadmap 中的拟议命令当成现成入口。
- 改公共语义：[CONTRACTS](../architecture/CONTRACTS.md)相关段落；目前总体仍 draft-0，配套同步生产者/消费者/测试。
- 查技术依据：[M0–M9](../roadmap/README.md)与[原始研究](../reference/README.md)，按需读取，不重复全仓研究。

## 什么算验证

| evidence_level | 可以证明 | 不能证明 |
| --- | --- | --- |
| source_review | 指定版本的实现、理论或文档一致性 | 已编译或运行成功 |
| build | 指定工具链产出文件 | 目标设备加载、真实HTP执行 |
| host_test | Windows CPU、fixture/mock的实际行为 | 完整FSR4、设备/游戏兼容或收益 |
| device_test | 指定设备/镜像/后端实测 | 所有游戏或其它系统自动通过 |
| game_test | 指定游戏/build/API/兼容栈/模型实测 | 其它组合自动通过 |

检查 gate：`not_run / pass / fail / blocked`。实现进度：`not_started / in_progress / blocked / complete`。计划中的“待设备/待依赖”是选择条件，不自动等于执行失败或blocked；只有已尝试且必需条件缺失时记录具体阻塞。没有实现不写“已实现未测”，没有实际数据不填0。

- skipped 必须给原因，不算 pass。跨venv补测要按不同测试去重，保留原命令的跳过数量。
- 基线环境不包含全部NumPy/ONNX/QAIRT依赖；当前多环境命令见[环境入口](../../tools/host/README.md)，统一聚合仍属待办。
- P5/P6证明自有小图；P6实际后端是QNN CPU。P7是提取；P8仅固定pass0的两种CPU实现对照，没有完整FSR ONNX或pass1–13验收。
- W8A8说明位宽，不与signed INT8互斥；记录实际signedness、scale/offset convention、量化粒度与外部I/O。传入HTP参数不等于HTP执行。
- 数值实验固定来源、输入、独立预期、事先容差、实际误差和输出哈希；两实现共享权重来源时明确局限。没有官方golden就不能证明官方等价。
- timeout、failure或close不证明真实后端已经停止；合成生命周期通过不证明GPU/NPU释放安全。

## 最小证据包

一个[短批次记录](../templates/batch-note.md)：ID、目标、base/diff身份、实际模型参数、实际环境/backend、完整命令/退出码、输入输出来源/重要哈希、审阅、失败/skips/未测和下一步。原始大日志、SDK、权重放忽略目录；可共享文档不能只依赖某人的绝对路径或未提交审计文件才能理解结论。

已有资产只在当前本地部署；新检出先核验，缺输入不伪造哈希、不自动覆盖现有venv。历史下载/包依赖问题若已解决，不重复列为阻塞；尚存风险要链接到具体新批次。

不预建整套空runtime/adapter/Decky目录。先定义一个可测使用者再增加模块。设备和游戏门槛始终独立；规划完成不代表实现完成。
