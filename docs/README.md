# 文档地图

维护日期：2026-09-22。默认环境是 Windows、无 Odin 3。当前已有主机工具、QAIRT小图QNN CPU链路、FSR材料提取和pass0参考；不是可用的完整超分产品。

## 最短阅读路线

| 目的 | 先读 | 再读 |
| --- | --- | --- |
| 看进展、决定下一批 | [STATUS](STATUS.md) | 对应计划中的叶子批次 |
| 无设备继续开发 | [HOST_PREPARATION](roadmap/HOST_PREPARATION.md) | 相关工具README、源码、测试 |
| 接设备后实施 | [DEVICE_EXECUTION](roadmap/DEVICE_EXECUTION.md) | 对应M0–M9技术章节与实际设备资料 |
| 查已完成成果 | [H/P历史索引](roadmap/COMPLETED_HOST_BATCHES.md) | 对应日期验证记录 |
| 协作与交接 | [AGENTS](../AGENTS.md)、[轻量流程](ai/MULTI_AGENT_WORKFLOW.md) | [单次提示](ai/SINGLE_RUN_PROMPT.md)、[证据速查](ai/IMPLEMENTATION_GUIDE.md) |
| 查架构/API边界 | [公共合同](architecture/CONTRACTS.md) | [里程碑索引](roadmap/README.md) |
| 查最初研究依据 | [研究归档](reference/README.md) | 固定版本来源；不是当前状态 |

[Goal模板](ai/GOAL_PROMPT.md)仅供显式连续目标使用；不默认开启。日常只写一份[短记录](templates/batch-note.md)，其它模板是复杂实验的可选项。

## 现有工具

| 范围 | 入口 |
| --- | --- |
| Python/venv预检、基线测试 | [host](../tools/host/README.md) |
| 设备档案采集、校验、脱敏 | [device](../tools/device/README.md)、[schema](../tools/device/schema/README.md) |
| 外部材料登记/核验 | [assets](../tools/assets/README.md) |
| PE/ELF与固定SDK清单 | [abi](../tools/abi/README.md) |
| 自有ONNX小图CPU参考 | [reference](../tools/reference/README.md) |
| QAIRT冒烟、小图W8A8/QNN CPU | [qairt](../tools/qairt/README.md) |
| 真实FSR材料提取、pass0对照 | [fsr](../tools/fsr/README.md) |
| 合成元数据/数值/生命周期 | `tools/model/`、`tools/replay/`及对应测试；范围见H/P历史索引 |

## 哪些页面随进展更新

- STATUS 是实时进度与下一步的唯一入口；R/F/E、D计划定义依赖/验收，不在每个README复制一份状态。
- README中英版同步能力边界；工具README只写真实可用命令，拟议CLI留在路线文档并明确标注。
- M0–M9保存详细技术条件，不要求每次任务通读；旧的整套工作卡/多报告提示服从当前轻量流程。
- `validation/`中的日期报告、`reference/`正文、`ai/FIRST_BATCH.md`保留原时点事实。新审计问题进入新任务和记录，不把历史成功改写成“当时没有成功”，也不把旧complete当成没有剩余缺陷。
- 模型/SDK/日志在忽略目录；可共享的状态与计划不得只链接个人电脑上的未提交报告。当前审计结论和任务映射已整理进计划及[本轮记录](validation/host/2026-09-22-documentation-roadmap-refresh.md)。
