# 已完成的主机批次（历史索引）

本页冻结 H1–H4、P1–P9c 当时的有限验收范围，避免把历史完成项重新放回活动队列。详细限制与当前结论见 [STATUS](../STATUS.md)；后续工作见[Windows 无设备活动计划](HOST_PREPARATION.md)。`complete` 只表示表中范围已有历史记录，不覆盖后来审计出的修复项，也不证明设备、HTP、游戏或完整 FSR4。

| ID | 原验收范围（紧凑摘要） | 历史记录 |
| --- | --- | --- |
| H1 | Windows 显式解释器/隔离环境复现 M0 unittest 与 fixture→validate→redact 链 | [H1 基线](../validation/host/2026-09-20-h1-windows-baseline.md) |
| H2 | synthetic manifest/tensor 的字段、shape/dtype/layout、容量与畸形输入校验 | [H2 元数据](../validation/host/2026-09-20-h2-manifest-metadata.md) |
| H3 | 小尺寸量化/反量化、舍入/饱和、平移/MV 重投影/reset 的独立 CPU 预期 | [量化参考](../validation/host/2026-09-20-h3-quantization-reference.md)、[空间参考](../validation/host/2026-09-20-h3-spatial-reference.md) |
| H4 | Python 同帧生命周期：完整身份、单在途、消费确认、timeout/reset/失败隔离与显式完成后回收 | [身份与在途](../validation/host/2026-09-20-h4-identity-inflight.md)、[消费/超时/reset](../validation/host/2026-09-20-h4-consumption-timeout-reset.md) |
| P1 | Windows 可重建环境入口、版本/架构/冲突预检和明确解释器 | [P1 环境](../validation/host/2026-09-20-p1-windows-environment.md) |
| P2 | 外部资产来源/版本/哈希登记、目录边界与只读核验 | [P2 资产](../validation/host/2026-09-21-p2-external-asset-verification.md) |
| P3 | 固定 QAIRT 2.49.0.260730、独立 Python 3.12 环境和 Windows 工具 help/能力快照 | [P3 QAIRT 工具](../validation/host/2026-09-21-p3-qairt-windows-host-tools.md) |
| P4 | 自有 PE/ELF 解析、变体/Verneed 回归和固定 SDK 候选 inventory；缺件如实记录 | [合成 ABI](../validation/host/2026-09-21-p4-synthetic-abi-inspector.md)、[ELF 变体](../validation/host/2026-09-21-p4-elf-variants.md)、[Verneed](../validation/host/2026-09-21-p4-multi-verneed.md)、[QAIRT inventory](../validation/host/2026-09-22-p4-qairt-abi-inventory.md) |
| P5 | 自有 Conv→Add→ReLU ONNX 小图、三类输入、独立 CPU 预期与 `1e-6` 容差 | [P5 ONNX/CPU](../validation/host/2026-09-21-p5-onnx-cpu-reference.md) |
| P6 | 自有小图 ONNX→DLC→W8A8/B32→metadata→QNN CPU；三例 `atol=0.01` | [P6 QAIRT 小图](../validation/host/2026-09-22-p6-qairt-small-graph-w8a8.md) |
| P7 | 固定公开镜像五输入、提取器/provider 交叉核验及本地 NPZ/graph 产物 | [P7 FSR v07 接收](../validation/host/2026-09-21-p7-fsr-v07-intake.md) |
| P8 | **仅 pass0**：真实 P7 权重的上游 simulator 与独立标量参考 0-LSB 对照；**没有 FSR ONNX，也不是 pass1–13/完整网络** | [P8 pass0 CPU](../validation/host/2026-09-21-p8-fsr-pass0-cpu-cross-check.md) |
| P9a | Python 生命周期的资源数量/逻辑容量上限、背压与完成后回收 | [P9a 资源预算](../validation/host/2026-09-21-p9a-resource-budget-backpressure.md) |
| P9b | 有界消费/reset 去重、窗口内幂等、冲突及过期通知拒绝 | [P9b 幂等](../validation/host/2026-09-21-p9b-bounded-idempotency.md) |
| P9c | 合成 execution-failure/close、候选 history 隔离与迟到完成回收 | [P9c 失败/关闭](../validation/host/2026-09-21-p9c-failure-close.md) |

共同边界：这些记录没有证明真实 FSR4 完整网络、GPU 前后处理、QNN/HTP 设备执行、Linux/Armada ABI、真实游戏接入、画质、帧率、延迟、温度或功耗。2026-09-22 审计发现的竞争、严格解析、M0 事务、环境/收据绑定及未固化回归，不回写篡改历史记录；它们以 R 批次进入活动计划。
