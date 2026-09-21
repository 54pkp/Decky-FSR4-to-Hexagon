# 单次小批次提示

默认选择 GPT-5.6 Sol / medium。复制下面全文；如已指定批次，在开头补充 ID。不要再用“从 P1–P9 选未完成项”：H/P 已结束，最新队列以 STATUS 为准。

```text
请为 https://github.com/54pkp/Decky-FSR4-to-Hexagon.git 完成一个小批次。

优先使用当前目录中 origin 匹配的仓库；否则只检查当前用户 Documents/GitHub/Decky-FSR4-to-Hexagon。不存在则创建父目录并克隆；已被无关内容占用则停止。先检查 Git 状态，干净且可快进才同步；保留已有修改，不全盘搜索、不重置/清理、不强推。

读取 AGENTS.md、docs/STATUS.md、docs/ai/MULTI_AGENT_WORKFLOW.md 和本提示，再按 STATUS 进入对应计划。默认 Windows、无 Odin 3，只从当前无设备 R/F/E 队列选择一个依赖满足的未完成叶子批次；优先 STATUS 的下一步。H1–H4、P1–P8/P9a–c 是历史完成项，不重启。分组中的子批次分别执行，不一次包办整个阶段。只有本次明确要求设备工作且设备/授权就绪时才选择 D 批次。

协调/集成/沟通使用实际 GPT-5.6 Sol medium；有独立工作才使用最多三位 Sol medium worker，文件范围不重叠且不再派生。实质代码、测试、合同或重要验收变化交实际 GPT-6 Astra medium 审冻结 diff（含新增文件）。不能只在提示中声明模型；不支持时如实说明。协调者是唯一 Git 和共享 STATUS 写入者。

实现选定行为、运行相关检查、修复审阅问题并必要复审。仅写一份短批次记录并更新 STATUS。保持显式解释器和隔离环境；本地 SDK/权重不随源码存在，新机器先核验。记录失败原因与未测项；CPU/mock/QNN CPU 不能冒充完整FSR4、HTP、设备或游戏验证。缺设备不阻塞独立无设备批次，不自动安装Linux/WSL或准备游戏。

按仓库流程提交并推送本批变更，先核对GitHub身份与远端，不使用unknown作者，不夹带他人修改。失败时保留本地变更/提交和具体原因，不强推或盲目重试。完成这一批后立即停止，汇报结果、审阅、提交/推送状态并留下一个下一步。不继续下一批，不创建Goal或定时任务。
```

[状态](../STATUS.md) · [无设备批次](../roadmap/HOST_PREPARATION.md) · [设备批次](../roadmap/DEVICE_EXECUTION.md)
