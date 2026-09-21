# 2026-09-22 / 文档同步与后续小批次重排

- 目标：把审计后的事实、开放问题和后续批次整理为可接续文档；本批不修实现、不启动新队列、Goal或定时任务。
- 基准：`574a80229b58e0dd678532ce373055bbbb83a128`；开始时工作树干净，fetch后与origin/main一致。
- 范围：中英README、AGENTS、STATUS、AI流程/提示、文档地图、主机/设备计划、M节点导航、工具说明和可选模板；3个agent TOML只同步默认主机/显式设备分配说明，不改model/effort参数。日期验证记录与原始研究正文保留；FIRST_BATCH只加归档导航，公共合同只加范围说明，不改协议语义。
- 角色：三个worker通过实际工具参数使用`gpt-5.6-sol / medium`；协调者当前会话型号/强度没有本批独立回执，记unknown，不以配置文件冒充切换。重要任务/验收边界交`gpt-6-astra / medium`复核，结论见下。
- 信息职责：STATUS管实时状态；R/F/E与D计划管ID、依赖、验收；COMPLETED_HOST_BATCHES保留H/P闭合范围；工具README管真实CLI；日期记录管证据。新克隆无需读取本机ignored审计文件才能理解新任务。

## 审计事实与欠账移交

2026-09-22前一轮审计在上述代码基准实跑基线233项（199 pass、34 skipped），专用环境补跑33个不同测试，另1项Windows固定skip手工复核。P3真实快照冒烟、P4真实ZIP清单、P5 CPU、P6真实转换/量化/QNN CPU、P7重新提取及P8 pass0均通过；不是设备/游戏证据。本轮不把这些历史复跑冒称为文档产生的新能力。

| 仍开放的问题 | 源码/证据入口 | 后续归属 |
| --- | --- | --- |
| 并发创建失败后可能清理他人目录，两处已复现 | `tools/reference/small_graph.py`、`tools/qairt/small_graph_pipeline.py` | R01、R02 |
| bitwidth=8.5及非法is_symmetric被接受，已复现 | `small_graph_pipeline.py` encoding解析 | R03 |
| 路径check/open替换、脱敏中途写失败残留，已复现 | `tools/device/profile_tools.py`；[历史残余](../M0/2026-09-20-first-batch-rereview.md) | R04、R05及D的POSIX验证 |
| P6从展开SDK执行，receipt只绑定部分入口；环境/模块闭包不全 | P6执行环境、SDK文件列表和receipt构造 | R的QAIRT快照/环境子批 |
| P7/P8信任边界、环境receipt与旧artifact歧义 | `tools/fsr/intake.py`、`pass0_check.py`；[P7](2026-09-21-p7-fsr-v07-intake.md)、[P8](2026-09-21-p8-fsr-pass0-cpu-cross-check.md) | R的收据/索引子批 |
| P7语义负例、P9压力检查未全部固化，symlink固定skip | `tests/fsr/test_intake.py`、`tests/replay/test_lifecycle.py`、`tests/device/test_collect.py` | R的回归/聚合子批 |
| P3继承管道超时，P4 POSIX发布竞态，Linux特有行为未测 | [P3](2026-09-21-p3-qairt-windows-host-tools.md)、[P4](2026-09-22-p4-qairt-abi-inventory.md) | R超时回归及D平台批次 |

P8仅pass0，尚无完整FSR主图/ONNX验收；P6是自有小图的unsigned W8A8/B32 QNN CPU，不是signed i8 FSR或HTP。SDK的3项包内缺件、3个超限库未解析、实际设备匹配unknown均保留。已解决的Python3.12/jsonschema、下载中断、NumPy冲突、onnx/protobuf缺失不重复登记阻塞。

## 本轮检查与边界

| 检查 | 实际结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m unittest discover -s tests -p test_*.py` | exit0；233项，199通过、34跳过；未修改任何Python实现/测试 |
| worker核对的11个工具CLI `--help` | 全部exit0；使用各工具要求的显式解释器，不安装依赖 |
| QAIRT环境：`-m unittest tests.qairt.test_probe tests.abi.test_inspector tests.abi.test_inventory tests.qairt.test_small_graph_pipeline -v` | exit0；54/54通过，不是新的SDK转换或HTP实测 |
| Python3.12 `tomllib`解析项目/角色配置 | 4个TOML均通过；只改3个角色的说明文字 |
| Markdown相对链接、队列ID/依赖及中英首页一致性 | 78份Markdown、245条本地链接检查无问题；86个叶子（R20/F15/E10/D41），无重号或未知依赖ID；人工核对中英入口一致 |
| `git diff --check` | exit0；实现/测试/模型文件无改动 |
| Astra文档/验收边界审阅 | `gpt-6-astra / medium`最终`pass`；已修M导航设备条件冲突、D必需host依赖可选化，澄清D13仅build和D31c/Decky可选边界；未见依赖循环，不代表任何新运行时gate |

- 未测：本轮不重跑SDK/FSR实验、不构建新运行时；Linux、HTP、Odin3、游戏、画质与性能仍not_run。R/F/E/D新批次全部not_started，历史H/P的complete仅保留原范围。
- Git交付：协调者已核对origin、main分支及作者`54pkp <67623881+54pkp@users.noreply.github.com>`，仅暂存本批42份文档/说明文件；本记录随本批提交，实际提交与正常推送结果以Git历史及任务最终回复为准，不提交SDK/模型/ignored产物。
- 下一步：R01，修复P5导出目录所有权竞争并增加确定性回归。此次只规划，不继续实现。
