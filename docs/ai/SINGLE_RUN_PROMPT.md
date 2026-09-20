# 单次小批次可复制提示

在全新 Windows 任务中选择 **GPT-5.6 Sol / medium**，复制下框全文：

```text
在 Windows 上为 Decky FSR4 to Hexagon 完成一个主机 CPU 小批次。先自举：若当前目录是 Git 仓库且 origin 规范化后等于 https://github.com/54pkp/Decky-FSR4-to-Hexagon.git，就原地使用；否则只检查 $USERPROFILE/Documents/GitHub/Decky-FSR4-to-Hexagon。目录不存在便从该 URL 克隆；存在但不是匹配仓库则停止说明。禁止全盘搜索、覆盖目录、固定预设 SHA、reset --hard、git clean 或 force-push，并保留现有修改。

进入仓库后读 AGENTS.md、docs/STATUS.md、docs/ai/MULTI_AGENT_WORKFLOW.md，检查分支、HEAD、工作树、origin 和必要证据。干净且可快进时同步远端，否则保留现场。从 STATUS 当前活动的 Windows/CPU 队列按依赖选一个未完成且可验收的小批次。H1–H4 已完成；当前 P1–P9 的材料、边界和验收见 docs/roadmap/HOST_PREPARATION.md。先做 P1 环境入口、P2 资产核验，再按条件准备 QAIRT、检查 ABI、跑自有小图、转换和真实资产参考，P9 可独立加固生命周期。实现、相关测试和简短记录缺一不可；不要启动 Goal 或调度，不扩到 M0–M9 最终硬件发布，不重做已通过项。

你是 Sol medium 协调者、唯一 integrator 和 Git 写入者。仅有独立工作时按需并行最多 3 位 Sol medium worker，划定不重叠路径且禁止其再派生。集成并运行相关检查；实质代码、合同或测试变更交 Astra medium 审真实 diff、源码和证据，轻微文档由 Sol 检查。完成审阅发现的相关修复、复测和必要复核。只写一份简短批次记录并更新 STATUS，不强制独立 work card、review packet 或 handoff。

日常只要求 Windows/CPU，不要求 Linux/WSL 或 Odin 3。使用仓库 .venv 的显式解释器；QAIRT/参考图依赖按批次在独立环境中安装。CPU、fixture、mock、QNN CPU 不算 FSR4 HTP、设备或游戏验证；缺设备不阻塞本批。缺合法模型/SDK 时选资产无关批次；安装、转换、真实权重实验的必需条件未满足，不得仅凭 mock 写成完成。确无可做批次时才请求最小输入并停止。审阅通过可提交并推送当前跟踪分支；核对已确认的 GitHub 身份和远端，不使用历史 unknown 作者、不覆盖他人改动。失败时保留改动和证据并做可行修复，不以丢弃制造通过。更新 STATUS 后停止，不自动选择下一批；报告改动、验证、审阅、提交/推送状态和缺口。
```
