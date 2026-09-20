# Goal 模式可复制提示

在 Windows 的 Codex 中选择 **GPT-5.6 Sol / medium**，输入 `/goal` 后粘贴下框全文。只运行 Windows/CPU 阶段；不会自动启动设备开发。用法依据：[OpenAI Goal 文档](https://learn.chatgpt.com/docs/long-running-work)。

```text
在 Windows 上持续完成 Decky FSR4 to Hexagon 当前主机 CPU 阶段。先自举：若当前目录是 Git 仓库且 origin 规范化后等于 https://github.com/54pkp/Decky-FSR4-to-Hexagon.git，就原地使用；否则只检查 $USERPROFILE/Documents/GitHub/Decky-FSR4-to-Hexagon。目录不存在便从该 URL 克隆；存在但不是匹配仓库则停止说明。禁止全盘搜索、覆盖目录、固定预设 SHA、reset --hard、git clean 或 force-push，并保留现有修改。

进入仓库后读 AGENTS.md、docs/STATUS.md、docs/ai/MULTI_AGENT_WORKFLOW.md，检查分支、HEAD、工作树、origin 和必要证据。干净且可快进时同步远端，否则保留现场。以启动时 STATUS 当前活动队列的未完成项冻结为本 Goal 唯一目标；H1–H4 已完成，当前为 P1–P9，详细材料、依赖和验收见 docs/roadmap/HOST_PREPARATION.md。各项均须有实际实现/执行、相关检查和简短记录，理论文档不能代替环境安装、模型提取或转换成功。按依赖队列续跑；资产条件阻塞时先做独立分支，不重做已通过项，不把 M0–M9 最终硬件发布作为 Goal。

你是 Sol medium 协调者、唯一 integrator 和 Git 写入者。每批取一个小包；仅有独立工作时按需并行最多 3 位 Sol medium worker，划定不重叠路径且禁止其再派生。实质代码、合同或测试批次由 Astra medium 审真实 diff、源码和证据，轻微文档由 Sol 检查；修复发现并复测。每批只写一份简短记录并更新 STATUS，不强制独立 work card、review packet 或 handoff。

日常只要求 Windows/CPU，不要求 Linux/WSL 或 Odin 3。使用仓库 .venv 的显式解释器，SDK/模型参考依赖保持独立环境。CPU、fixture、mock、QNN CPU 不算 FSR4 HTP、设备或游戏验证；缺设备不阻塞本阶段。缺合法模型/SDK 等资产时先做全部资产无关项，必需项未实现不得 complete；无可做项时才请求最小输入，保留明确阻塞而不假称阶段完成。审阅通过可提交并推送当前跟踪分支；先核对已确认的 GitHub 身份和远端，不使用 unknown 作者、不覆盖他人改动。失败时保留改动和证据并定点修复，不以丢弃制造通过。仅当启动时冻结的活动主机队列验收全部通过，更新 STATUS、核对提交/远端并将 Goal 标为 complete；这不代表 M0–M9 complete。
```
