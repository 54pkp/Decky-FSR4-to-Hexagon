# 验证报告模板

> 可选详细模板，留待复杂实验使用。当前 Windows/CPU 批次只用 [batch-note](batch-note.md)，不要求按本模板额外生成文件。

这是模板，不是真实测试结果。需要详细报告时，主机批次使用 `docs/validation/host/YYYY-MM-DD-<batch>.md`，设备批次使用对应 `docs/validation/Mx/`；沿用本批唯一记录，不另复制一份。替换占位内容，未运行项保留 `not_run`。原始数据放忽略目录，模板本身不是验收证据。

## 基本信息

```yaml
report_schema_version: draft-0
run_id: null
milestone: null
work_package: null
source_commit: null
dirty_tree: null
started_at: null
finished_at: null
evidence_level: null # source_review/build/host_test/device_test/game_test
gate: not_run # not_run/pass/fail/blocked
device_profile_id: null
model_manifest_id: null
service_instance_id: null
actual_backend: null # 例如 HTP/CPU/mock/none，以实际执行路径为准
```

## 本次目标和适用范围

- 要验证的具体行为：
- 本次不覆盖的行为：
- 依赖报告与通过门槛：
- 目标平台/游戏/API/profile/模式：

## 环境与资产

| 项目 | 实际值及来源 |
| --- | --- |
| 主机、目标架构、OS/镜像/内核 | 待填 |
| CPU/GPU/NPU、驱动、固件 | 待填 |
| libc、工具链、QAIRT/runtime | 待填 |
| Steam/Proton/FEX/DXVK/vkd3d/Decky | 待填或注明不适用 |
| 模型/context/shader/输入序列 SHA-256 | 待填 |
| 游戏构建与可执行文件哈希 | 待填或注明不适用 |
| 配置、功率/温度/亮度/风扇/帧率上限 | 待填或注明不适用 |

## 检查记录

| 检查 ID | 层级 | 前置条件 | 实际命令/操作 | 退出码 | 观察结果 | gate | 证据路径与哈希 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填 | 待填 | 待填 | 未执行 | null | 无 | not_run | 无 |

保留完整 argv、工作目录、必要环境变量和工具版本；敏感凭证脱敏。长日志不复制进表格，引用原始产物并写出关键错误/输出。手动游戏操作写明场景、动作、次数和记录方法。

## 正确性、计数与失败路径

- 输入/输出对应：session/context/frame/history generation 如何核对？
- HTP、fresh output、cached redisplay、writeback、fallback 是否分别统计？
- 测试故障：断连、坏包、错模型、超时、退出、输出失败等实际覆盖哪些？
- 已观察到的错误码、第一现场与恢复过程：
- 不可重现/参考不可得/日志缺失等限制：

## 性能与质量（不涉及则说明）

阶段耗时、单位、clock domain、warm-up、样本数、p50/p95/p99、队列深度和帧年龄分别记录。输入到显示延迟说明测量方法；功耗报告时间积分方法和实际帧数。明确重复次数、场景一致性、异常/排除数据及理由。

画质说明参考版本、输入序列、逐阶段误差和动态缺陷，不只报告一张截图的 PSNR。没有 FP 参考时写明不能证明何种等价性。

## 结论与交接

- 本检查 gate 及理由：
- 能证明的范围：
- 不能证明的范围：
- 节点是否全部通过；若否，剩余检查：
- 下一工作包、依赖和报告链接：
- 是否修改状态页或合同；对应变更：
