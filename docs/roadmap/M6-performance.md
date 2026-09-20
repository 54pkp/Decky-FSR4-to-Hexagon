# M6：性能、延迟与能耗决策

> 状态：路线设计；本节点尚未实现或在 Odin 3 上验证。文中工具、配置和字段除公共合同外均为拟议接口。

先读 [AI 实施指南](../ai/IMPLEMENTATION_GUIDE.md)、[公共合同](../architecture/CONTRACTS.md)、[项目状态](../STATUS.md) 和 [归档研究](../reference/2026-09-20-feasibility.zh-CN.md)。本节点的结果决定哪些模式可以推荐给用户；得到负面结果同样是有效产出，不能为了显示收益删除不利样本。

## 1. 目标与边界

目标是在 AYN Odin 3 / 已锁定 Armada 环境上，说明 FSR4 NPU 路径把时间和能量花在哪里，并判断实际交互收益。先保留 M4/M5 同帧复制基线，再逐项评估优化。

本节点交付测量工具、原始数据索引、可重现报告和默认模式决策，不承诺一定提高 FPS 或续航。不通过降低输入质量、丢弃困难场景、重显旧帧或偷偷切换 CPU 后端制造收益。

范围包括 GPU readback/upload、CPU packing、IPC、GPU 前后处理、QNN graphExecute、等待、排队和显示行为。游戏自己的渲染时间与项目开销分别记录。

非目标：新增游戏 API、换一代 FSR 模型、开发 Decky UI、给 NPU 强制超频、修改热管理、把多帧异步结果冒充同帧重建。

## 2. 依赖与无设备工作

- 硬件验收依赖 M5 已通过的固定组合，并继承其 `device_profile_id`、`model_manifest_id` 和画质基准。
- M4 的同帧正确性版本必须保留为可回退构建，不能直接在唯一基线上堆叠优化。
- 没有设备时可实现事件 schema、统计脚本、模拟 trace 和报告生成器；只能记为 `build` / `host_test`。
- 没有输入延迟测量装置时可先做阶段计时，但“实测输入延迟”保持 `not_run`，不以推算值补齐。
- 若功率传感器不可用，报告缺项并准备外部仪表方案；不能把 QNN profile 的估算替代整机测量。

## 3. 固定源码参考

- [上游测量与异步队列说明](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/WHITEPAPER.md)：RP6 的作者结果，只作测量设计参考。
- [上游 live daemon](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/live_daemon.c) 与 [QNN service](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/daemon/qnn_service.c)：定位 GPU/NPU/队列边界。
- [fork 的同步 Vulkan 复制路径](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/layer/src/layer_entry.cpp) 与 [QNN runtime](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/daemon/src/qnn_runtime.cpp)：借鉴资源与执行测量点，不能复用 XLSR tile 时间为 FSR4 整帧时间。
- [fork 状态计时](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/daemon/src/main.cpp)：`upscale_frame` 包含 CPU 工作，名称不能直接当纯 NPU latency。

引用上游数值时必须写作者、设备、版本与测量范围；不能预测 8 Elite 比 RP6 快多少。

## 4. 建议模块与产物

```text
tools/bench/schema/trace-v1.json       # 事件与 run 元数据合同
tools/bench/capture.py                # 收集、校验、标记缺失事件
tools/bench/analyze.py                # 分位数、功率积分、计数核对
tools/bench/compare.py                # 配对比较，不覆盖原始数据
tools/bench/fixtures/                 # 小型合成 trace 与异常样本
docs/benchmarks/odin3-<date>.md        # 面向工程决策的结果
docs/validation/M6/<date>-<batch>.md   # 闸门与证据索引
artifacts/M6/<run_id>/                # 大体积原始数据，默认不入库
```

运行时插桩放在现有模块边界，复用统一帧身份，不另造无法关联的“性能帧号”。用构建开关控制详细 trace；记录插桩开销。

## 5. 分批实现路线

### M6.1 冻结实验设计

1. 固定游戏构建、存档/回放、相机路径、分辨率、画质、帧率上限、显示刷新率和亮度。
2. 固定供电状态、风扇策略、环境温度与预热规则；电池充电电流不能直接当系统负载功率。
3. 为每组写清问题和预注册判据，至少包含以下基线：

| 组别 | 用途 |
| --- | --- |
| 原生目标分辨率，无本项目 | 游戏原始表现 |
| 相同低分辨率 + 已有可用上采样 | 分离降低渲染分辨率本身的收益 |
| NPU 同帧复制基线 | 已通过 M5 的正确性与完整成本 |
| 每次一种优化 | 明确收益来源与副作用 |

输出实验清单和 `run_id` 生成规则；不能在看到结果后只保留最有利场景。

### M6.2 全链路计时与计数

1. 在 adapter Evaluate 入口/退出、readback 完成、编码、发送、接收、GPU pre、QNN、GPU post、上传及消费处记录事件。
2. CPU 使用单调时钟；GPU 使用 timestamp/query 并明确可用性与分辨率。跨时钟域必须校准或分别报告，不能直接相减。
3. 同时记录 `service_instance_id`、`session_id`、`context_id`、`frame_id`、`history_generation`、实际后端、队列深度和丢弃原因。服务重启时实例 ID 换新，旧计数不拼接成连续运行。
4. 分开统计 `evaluate_requests`、`htp_execute_successes`、`fresh_results`、`output_writebacks`、`cached_redisplays`、回退、超时、失败和显示次数；新结果生成与游戏成功写回不能合并。
5. 异步实验明确输入帧号与输出源帧号；帧年龄既报帧数也报毫秒，不能以显示次数计算“有效 NPU FPS”。
6. 对未知显示时点写 `unknown`；Evaluate 完成不是屏幕发光，提交 present 也不是物理显示。

输出可以从一帧追到所有阶段的 trace，并用小样本手工复算。不要简单相加有重叠的阶段耗时后称为关键路径。

### M6.3 建立统计与能量报告

1. 热稳态判据由试跑确定并写入配置，例如温度/频率在指定窗口内无持续趋势；同时保存预热数据。
2. 每组至少 3 次独立热稳态重复；尽量交错 A/B 顺序，记录冷启动差异和异常运行原因。
3. 对帧时间与各阶段报告样本数、p50/p95/p99、均值和离散程度，说明 percentile 算法及缺失样本处理。
4. 单次运行和合并结果同时保留，避免把全部帧合并后掩盖运行间波动；小样本 p99 说明不确定性。
5. 采集功率时间序列并积分 `energy_j = ∫ power_w dt`，注明传感器范围、采样率和误差。
6. 同时报整机平均功率、总能量、时长、总显示帧、新输出帧；`J / fresh frame` 与 `J / displayed frame` 分开。
7. 报温度、GPU/CPU/NPU 可观测频率、节流、内存峰值、失败率；不可见项标缺失而非 0。

### M6.4 独立测量交互延迟

选择可重现按键到可见响应的场景，以高帧率相机或经验证的测量装置记录输入事件和屏幕响应；注明设备、帧率、触发定义及量化误差。

测量输入到显示的分布，与无项目和复制基线配对比较。没有物理测量时软件标记只能报告 `software_pipeline_latency`，保留 `input_to_photon` 未测状态。

若吞吐更高但画面年龄或输入延迟不可接受，保留该模式为实验或撤销；不能用较低 graphExecute 时间否定实测延迟恶化。

### M6.5 只优化已定位的瓶颈

推荐顺序：预分配与复用 buffer → 消除重复格式转换 → 原生共享内存 → GPU/NPU 注册内存互操作 → 有界流水实验。

每一步都需要证明少了哪些复制、等待或分配。memfd 只减少 IPC 复制；DMA-BUF 导出成功不等于 QNN 可注册，QNN 可注册不等于 GPU 图像布局可直接推理。

互操作小样例先验证分配器、格式/stride、cache ownership、同步和释放，再接游戏。跨 Wine/FEX 的 FD 或资源桥单独验证，不假设 WinSock 能发送 `SCM_RIGHTS`。

保持 bit-exact 的改动必须比较阶段输出和连续序列；浮点顺序、精度或模型变更造成非 bit-exact 时先提交误差解释与 M5 重验，不以“视觉差不多”放行。

## 6. 拟议数据合同

以下是设计样例，不能直接当已实现 API：

```json
{
  "run_id": "M6-example-a1",
  "device_profile_id": "<M0-id>",
  "model_manifest_id": "<M2-id>",
  "mode": "same-frame-copy",
  "warmup_rule": "<documented criterion>",
  "repeat_index": 1,
  "trace_clock": "monotonic",
  "evidence_level": "device_test",
  "gate": "not_run"
}
```

事件结构至少包含上述公共帧身份、事件名、时间戳单位、时钟域、字节数和结果类别。大整数在 JSON/JS 链路中用公共合同规定的无损表示，不隐式转为可能丢精度的 Number。

`fsr4hexctl` 将来可提供只读统计入口；本节点不得为了生成报告假造运行时计数。离线分析器必须拒绝混合模型/设备/会话的不可比输入。

## 7. 失败、回退与诊断

| 失败 | 判别证据 | 必须动作 |
| --- | --- | --- |
| FPS 上升但 fresh 帧不增 | 帧身份、cached 计数 | 报告为重显增加，不判性能收益 |
| graphExecute 快而总延迟慢 | 阶段 trace 与队列深度 | 定位传输/等待，不先换模型 |
| 温度持续升高或节流 | 温度/频率曲线 | 标无热稳态；延长预热或判该策略不可持续 |
| 共享内存偶发旧数据 | 帧水印、缓存一致性样例 | 关闭优化、回到复制基线 |
| 优化后轻微误差累积 | 多帧输出比较 | 回 M5，记录误差来源并复验 |
| tracing 明显拖慢 | 有/无插桩对照 | 降采样或离线缓冲，公开测量开销 |
| 功率缺失/计量范围不明 | 原始传感器元数据 | 能效结论 blocked，不填估计实测值 |

实验开关按 profile 控制；失败只禁用该实验模式，保留可用复制路径。删除实验资源前等待所有 GPU/NPU 消费完成。

## 8. 验收闸门

- `source_review`：计时范围、帧计数定义和能量公式得到审阅。
- `build` / `host_test`：统计脚本能识别乱序、缺失、重复、负时长、时钟域错误和混合 run。
- `device_test`：至少 3 次热稳态重复，完整 p50/p95/p99、功率/能量、唯一新帧与缓存帧分类。
- `game_test`：固定场景动态画质不退化，实测输入延迟及其误差有记录，失败恢复有效。
- 默认模式有明确设备/游戏范围与准入阈值；阈值在测量前约定，不能把单个 FPS 百分比作为全部准入条件。
- 所有 gate 使用 `not_run` / `pass` / `fail` / `blocked`，并链接原始数据；性能收益为负时可完成研究，但不得标推荐模式通过。

## 9. 交接与 AI 提示词

交接包包含构建 SHA、原始 trace 索引与哈希、实验配置、重复运行列表、画质复验、传感器误差、瓶颈排序、默认模式 ADR 和仍未测量项目。报告保存到 `docs/validation/M6/YYYY-MM-DD-<work-package>.md`，交接为同名 `-handoff.md`。下一步通常是把 M6 结论写入 M7 profile 与 M8 展示能力。

```text
实施 M6 的一个可审阅批次，先读取 docs/ai/IMPLEMENTATION_GUIDE.md、公共合同、
M4/M5 验证记录及本路线。先报告实际已有代码和证据，再实现所选批次。
保持同帧复制基线。所有事件关联 session/context/frame/history generation；
分别统计真实 HTP、新输出、cached、回退与显示次数，不以 graphExecute 代替输入延迟。
每次只改变一个优化变量，输出文件清单、可复现命令、原始数据索引和 gate 状态。
无 Odin 3 时只完成离线工具/host_test，并明确 device_test、game_test 为 not_run。
不要编造分数、硬件计数或能效结论；任何数值误差变化先回 M5 验证。
```
