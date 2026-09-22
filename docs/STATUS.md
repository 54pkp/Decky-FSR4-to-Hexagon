# 当前状态与下一步

更新：2026-09-22。事实基准：`574a80229b58e0dd678532ce373055bbbb83a128` 的代码审计与Windows复跑，以及后续文档刷新和R01验证记录。当前没有设备证据。

[文档地图](README.md) · [无设备批次](roadmap/HOST_PREPARATION.md) · [设备批次](roadmap/DEVICE_EXECUTION.md) · [单次提示](ai/SINGLE_RUN_PROMPT.md)

## 现在处于什么阶段

**Windows，无 Odin 3；主机准备完成一轮，核心产品运行时尚未实现。** 目标意图仍是 Odin 3 / Snapdragon 8 Elite / Armada OS，实际镜像、ABI、HTP和游戏路径均未验证。没有可安装插件、已验证游戏或性能/功耗数据。

| 已有成果 | 已验证范围 | 不能推出 |
| --- | --- | --- |
| M0采集/schema/校验/脱敏，H1–H4 | Windows fixture、合成数值、生命周期 | 真实设备采集、完整FSR或后端取消安全 |
| P1/P2 | 隔离环境入口、外部资产核验 | 新检出自动拥有本机SDK/模型 |
| P3/P4 | 固定QAIRT2.49.0.260730、工具冒烟、ABI候选清单 | Linux运行库可加载、FastRPC或HTP成功 |
| P5/P6 | 自有小图ONNX→W8A8/B32→实际QNN CPU执行 | FSR转换、HTP prepare/执行 |
| P7/P8 | 真实v07材料提取、pass0独立标量/上游CPU对照 | 完整pass1–13、FSR ONNX、官方golden等价 |
| P9a–c | 有界资源/幂等、失败/关闭的Python状态机 | 真实GPU/NPU资源静止、持久恢复 |

H1–H4、P1–P8/P9a–c保留 `complete` 的原批次范围；新发现不被这个标签豁免。范围、证据和已解决历史问题见[完成项索引](roadmap/COMPLETED_HOST_BATCHES.md)。不要重启旧P队列，也不要把准备项数量换算成整体完成百分比。

## 活动任务与状态规则

R队列已完成。下一批：**F03——组装pass1–13完整CPU主图并做端到端/逐层交叉检查。**

| 队列 | 当前实现状态 | 选择条件 |
| --- | --- | --- |
| R：审计修复、可复现性与回归 | R01–R13全部 `complete` | 本轮已结束；不重启已完成叶子 |
| F：真实FSR CPU/ONNX/QAIRT离线 | F01–F02c `complete`；其余叶子项 `not_started` | 当前连续目标；按依赖逐叶推进 |
| E：协议、自有测试host、部署/观测准备 | 所有叶子项 `not_started` | 后续工程分支；必须有具体可测使用者和工具链 |
| D：设备、游戏与交付验收 | 所有叶子项 `not_started`；所有设备/游戏gate `not_run` | 待设备及对应依赖/授权；不是自动失败或全部blocked |

完整ID、依赖与验收只在[HOST_PREPARATION](roadmap/HOST_PREPARATION.md)和[DEVICE_EXECUTION](roadmap/DEVICE_EXECUTION.md)定义。上表是这些计划中所有叶子ID的默认实时状态；开始或完成一项时在下面增加该ID的状态/证据，覆盖组默认值，不复制整套验收文字。

| 已开始的新批次 | 状态 | 证据 / 阻塞 |
| --- | --- | --- |
| R01 | `complete` | [P5导出目录所有权修复](validation/host/2026-09-22-r01-p5-export-ownership.md)；仅为Windows host_test |
| R02 | `complete` | [P6私有发布staging](validation/host/2026-09-22-r02-p6-private-publishing.md)；仅为Windows host_test |
| R03 | `complete` | [P6 encoding严格解析](validation/host/2026-09-22-r03-p6-strict-encoding.md)；仅为Windows host_test |
| R04 | `complete` | [M0 evidence打开对象绑定](validation/host/2026-09-22-r04-m0-evidence-open-binding.md)；仅为Windows host_test |
| R05 | `complete` | [M0公开脱敏整体事务](validation/host/2026-09-22-r05-m0-redaction-transaction.md)；仅为Windows host_test |
| R06a | `complete` | [QAIRT/P6前端环境重建](validation/host/2026-09-22-r06a-qairt-frontend-environment.md)；fresh Windows venv / CPU测试，不是SDK执行或设备验证 |
| R06b | `complete` | [P6固定SDK私有快照](validation/host/2026-09-22-r06b-p6-sdk-snapshot.md)；固定ZIP合成小图/QNN CPU，不是HTP或设备验证 |
| R06c | `complete` | [P6环境收据与漂移拒绝](validation/host/2026-09-22-r06c-p6-environment-receipt.md)；Windows v2 receipt / QNN CPU，不是HTP或设备验证 |
| R06d | `complete` | [P6缺失父目录诊断](validation/host/2026-09-22-r06d-p6-missing-parent.md)；Windows host_test |
| R07 | `complete` | [Windows文件symlink能力探测](validation/host/2026-09-22-r07-windows-symlink-capability.md)；本机真实分支pass |
| R08a | `complete` | [四venv聚合验证入口](validation/host/2026-09-22-r08a-multi-venv-verification.md)；4组completed，skip单列 |
| R08b | `complete` | [P3后代管道超时回归](validation/host/2026-09-22-r08b-descendant-pipe-timeout.md)；Windows真实后代句柄回归，不声称进程树终止 |
| R08c | `complete` | [公开Windows CI合同](validation/host/2026-09-22-r08c-public-windows-ci.md)；可公开重建的Python3.10.11/3.12.10 x64云端双job通过 |
| R09 | `complete` | [P7 graph/NPZ语义负例](validation/host/2026-09-22-r09-p7-semantic-negatives.md)；fsr-extract 14个独立语义场景实跑 |
| R10a | `complete` | [P7环境收据与stdout gate](validation/host/2026-09-22-r10a-p7-environment-receipt.md)；真实v07重跑生成v2 receipt |
| R10b | `complete` | [P8 accepted receipt信任链](validation/host/2026-09-22-r10b-p8-accepted-receipt.md)；固定R10a摘要并拒绝旧/自洽伪收据，仅为NumPy host CPU pass0 |
| R11 | `complete` | [P9a资源预算回归固化](validation/host/2026-09-22-r11-p9a-budget-regressions.md)；8类retained状态、身份/容量边界与永久背压，仅为CPU合成状态机 |
| R12a | `complete` | [P9b有界幂等回归固化](validation/host/2026-09-22-r12a-p9b-idempotency-regressions.md)；并发重试、32+窗口与namespace隔离，仅为进程内CPU状态机 |
| R12b | `complete` | [P9c失败/关闭回归固化](validation/host/2026-09-22-r12b-p9c-close-regressions.md)；五态、四代预算及64路竞态，仅为Python线程状态机 |
| R13 | `complete` | [当前artifact索引](validation/host/2026-09-22-r13-current-artifact-index.md)；固定P7/P8摘要并区分current、historical/stale与audit-temporary |
| F01 | `complete` | [pass1–13 CPU参考清单](validation/host/2026-09-22-f01-pass-manifest.md)；机器可验合同与固定小输入，独立预期仍为unknown |
| F02a | `complete` | [pass1–4 CPU参考](validation/host/2026-09-22-f02a-cpu-pass1-4.md)；固定小输入下vector/scalar/认证simulator逐层0 LSB，仅为host CPU |
| F02b | `complete` | [pass5–9 CPU参考](validation/host/2026-09-22-f02b-cpu-pass5-9.md)；group2/bin raw/CT2D/skip逐层0 LSB，仅为host CPU |
| F02c | `complete` | [pass10–13 CPU参考](validation/host/2026-09-22-f02c-cpu-pass10-13.md)；p10–12逐层0 LSB、p13 float16位模式0 ULP，仅为host CPU |

一次只选一个叶子项；a/b/c分别执行。F/E不是已实施能力，也不默认纳入某次连续目标。设备未接入不阻塞R及依赖已满足的F/E分支；新队列用尽或剩余项确有外部阻塞时再请求最小输入，不能自动扩展范围。

## 必须保留的审计欠账

- P5的check→mkdir创建竞争和P6正常双发布者竞争已由R01/R02关闭；创建成功后遭敌对路径替换的更强场景不在这两批证明范围。
- P6的小数/错误类型bitwidth和非法布尔metadata已由R03改为fail-closed；固定SDK小写字符串及原生布尔保留回归。
- M0 evidence路径检查/open竞争及公开输出中途失败残留已由R04/R05关闭；POSIX和设备侧仍未验证。
- P6固定SDK快照和环境收据绑定已由R06b/R06c关闭；P7/P8环境收据、消费者信任链与旧artifact分类已由R10a/R10b/R13加固。索引是源码信任根，未来切换current仍须显式审阅。
- P7 graph marker/count及NPZ 100-array/shape/dtype独立语义负例已由R09固化；P7环境/argv/stdout收据及P8对其固定摘要、来源和输出的信任链已由R10a/R10b固化。P9a/P9b/P9c历史附加资源、幂等与close/failure检查已由R11/R12a/R12b固化。多venv聚合检查已由R08a固化。
- P3后代管道超时的Windows有界返回与fail-closed诊断已由R08b关闭；不保证后代静止或进程树终止。P4 POSIX发布竞态及Linux特有行为仍需对应批次核查。
- 公开Windows x64 CI合同已由R08c固化；ARM64/Linux、私有多venv及设备仍为`not_run`，实际GitHub-hosted结果以push后Actions为准。
- 固定SDK清单有3项包内缺件、3个超限大库未解析；实际设备匹配unknown。详细范围和修复归属见两个计划。

这些是未修问题，不因本文更新而关闭。历史下载、Python3.12/jsonschema、ONNX/protobuf缺失已解决，不继续当成当前阻塞。

## 最近验证快照与环境

原始2026-09-22审计为基线233项、199 pass / 34 skipped；后续批次持续增加回归。F02c后当前本机基线为358项、271 pass / 87 skipped；需NumPy的FSR方法在公开基线准确skip，在fsr-extract环境实跑。R08a历史四venv聚合为399次执行观察（351 pass / 48 skipped），其中存在跨组重叠且不含后续新增测试。专用环境结果须单列，不能把skip写成pass。

- P3真实快照冒烟、P4真实ZIP清单、P7重新提取通过；完整QAIRT ZIP哈希匹配。
- P5三例误差：0 / 0 / 1.1920928955078125e-07。
- P6实际QNN CPU三例误差约0.002415 / 0.005603 / 0.007337，均小于预设0.01；实际per-tensor uFxp_8 / bias sFxp_32。
- P8仅pass0，固定样本最大差0 LSB。设备、游戏和性能均未运行。

本机基线、QAIRT、reference、fsr-extract为独立Python3.12.14环境；系统Python3.9保留。QAIRT使用NumPy1.26.4，reference/fsr使用NumPy2.2.6；具体重建/命令见[环境说明](../tools/host/README.md)及工具README。这些是本机核查值，不保证其它机器已有部署。

最近记录：[F02c pass10–13 CPU参考](validation/host/2026-09-22-f02c-cpu-pass10-13.md)；前一批：[F02b pass5–9 CPU参考](validation/host/2026-09-22-f02b-cpu-pass5-9.md)。

## 最终里程碑

M0整体仍 `in_progress`，缺真实设备建档/基线冻结；M1–M9运行时实现仍 `not_started`。H/P准备成果不自动通过M节点。硬件主线是M0→M1→M2，游戏分支M0→M3，两支汇合M4，再到M5/M6及M7/M8；M9为按需兼容扩展。

详见[里程碑技术索引](roadmap/README.md)。当前只默认推进R/F/E；接入设备后按D叶子批次逐步取得device/game证据。
