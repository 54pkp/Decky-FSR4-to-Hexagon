# M0 S0 schema contract handoff

## 当前现场

- 节点/工作包：M0 / S0，2026-09-20。
- 工作卡：`docs/ai/FIRST_BATCH.md`；owner：主 integrator。
- 实际模型/推理强度：主会话精确运行身份不可见；项目 `.codex/config.toml` 已读取，声明 `gpt-5.6-sol` / `medium`。
- 基线：`main` / `fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d`；S0 文件为共享工作区未提交新增文件，由 integrator 独占。
- 环境：Windows 主机、Python 3.12.7、jsonschema 4.26.0；无 Odin 3 设备访问。

## 已完成的变化

| 文件/模块 | 行为变化 | 验证报告 |
| --- | --- | --- |
| `tools/device/schema/device-profile.schema.json` | 固定 M0 最小报告、观察项、证据、私有/公开关系和严格额外字段策略 | `2026-09-20-schema-contract.md` |
| `tools/device/schema/README.md` | 固定输出目录、CLI、退出码、fixture 和 runner 协议 | 同上 |
| `tools/device/requirements-host.txt` | 锁定 `jsonschema==4.26.0` | 同上 |

## 尚未完成或验证

- A 尚未实现 collector；B 尚未实现离线工具、fixture 与测试。
- Linux live 模式、子进程超时回收、真实权限行为均为 `not_run`。
- Odin 3 `device_test: not_run`；SDK、专有资产、DSP/NPU、Steam 和游戏操作均未进行。

## 决定与合同

- JSON Schema 方言是 Draft 2020-12；项目数据合同版本仍为 `draft-0`。
- fixture 必须 `example_only: true` 且 `gate: not_run`；公开档案只能由离线 `redact` 产生。
- fixture 命令按完整 argv 数组精确匹配，不执行 fixture 中的程序；生产 runner 才能调用无 shell 的 subprocess。
- 未改变共享合同，不产生 ADR。后续若需改变这些冻结接口，应暂停并由 integrator 同步生产者、消费者和测试。

## 复现与下一步

1. 安装/核对 `tools/device/requirements-host.txt` 后执行验证报告中的三项主机检查。
2. Worker A 只写 collector、其 README 和独占报告；Worker B 只写离线工具、fixtures、tests 和独占报告。
3. 两者都不得操作 Git 索引、分支或公共状态页，也不得把主机 fixture 结果描述为设备验证。

