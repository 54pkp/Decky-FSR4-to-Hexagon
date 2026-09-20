# 证据速查与按需参考

日常流程只看 [轻量流程](MULTI_AGENT_WORKFLOW.md) 和 [STATUS](../STATUS.md)。本页不再重复派工、审阅和交接步骤。旧路线中的多份模板要求由轻量流程替代；历史实验本身保持原样。

## 什么算验证

| evidence_level | 可以证明 | 不能证明 |
| --- | --- | --- |
| source_review | 固定来源下的实现或理论推导，含假设 | 编译、CPU 运行或设备成功 |
| build | 指定工具链能生成产物 | ARM Linux 可加载、HTP 可执行 |
| host_test | Windows CPU、合成输入或 mock 的实际行为 | FSR4 HTP、游戏兼容、设备性能 |
| device_test | 指定设备/系统的实测 | 所有游戏可用 |
| game_test | 指定游戏/API/兼容栈/模型组合的实测 | 其它组合自动通过 |

单项 `gate`：`not_run / pass / fail / blocked`。实现进度：`not_started / in_progress / blocked / complete`。记录 skipped 和原因，不能折算成 pass。当前所有设备与游戏测试保持 `not_run`；H 阶段 complete 仅指主机范围，不替代 M 节点验收。

理论记录写清来源版本、假设、推导及尚未运行项。CPU 数值实验写清输入构造、公式/坐标约定、独立预期、容差和实际误差；不能调用被测实现来重新计算唯一的预期结果。合成算子测试不等于完整 FSR4 CPU 推理，更不等于 HTP 数值等价。真实模型可用后再固定版本、许可、输入与输出哈希，单列对照实验。

## 用到再读

- [公共合同](../architecture/CONTRACTS.md)：只读本批相关字段；草案不是现成 ABI，修改时同步生产者、消费者与测试。
- [M0–M9 详细路线](../roadmap/README.md)：未来设备/API/部署的参考，当前不逐项实施。
- [历史研究](../reference/README.md)、[已完成首批](FIRST_BATCH.md)：追溯来源，不重新执行。
- [短批次记录](../templates/batch-note.md)：日常唯一模板。目录内其它模板保留供复杂实验选用。

不预先创建全套 runtime、adapter、Decky、安装器空目录。先有一个可测使用者，再增加模块。`research/`、`.research-notes/`、SDK 和模型目录不随仓库分发，不能成为新电脑启动的隐式依赖。
