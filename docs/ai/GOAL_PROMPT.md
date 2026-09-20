# Goal 模式可复制提示

在 Windows 的 Codex 中选择 **GPT-5.6 Sol / medium**，输入 `/goal` 后粘贴下框全文。只运行 Windows/CPU 阶段；不会自动启动设备开发。用法依据：[OpenAI Goal 文档](https://learn.chatgpt.com/docs/long-running-work)。

```text
在 Windows 上持续完成 Decky FSR4 to Hexagon 当前主机 CPU 阶段。先自举：若当前目录是 Git 仓库且 origin 规范化后等于 https://github.com/54pkp/Decky-FSR4-to-Hexagon.git，就原地使用；否则只检查 $USERPROFILE/Documents/GitHub/Decky-FSR4-to-Hexagon。目录不存在便从该 URL 克隆；存在但不是匹配仓库则停止说明。禁止全盘搜索、覆盖目录、固定预设 SHA、reset --hard、git clean 或 force-push，并保留现有修改。

进入仓库后读 AGENTS.md、docs/STATUS.md、docs/ai/MULTI_AGENT_WORKFLOW.md，检查分支、HEAD、工作树、origin 和必要证据。以启动时 STATUS 的 H1–H4 本阶段清单冻结为本 Goal 唯一目标：H1 Windows M0 测试基线/可复现入口；H2 用合成 fixture 做资产无关 manifest/tensor 元数据校验；H3 CPU 合成数值参考，覆盖量化/反量化、已声明坐标的平移/重投影/reset 样例，但不冒充完整 FSR4；H4 串联 H2/H3 的同帧单请求生命周期 CPU 回放，覆盖帧身份、过期拒绝、超时不得释放在途资源和显式完成后回收。四项均须有实现、测试和简短记录，理论文档不能替代；实际 FSR4 权重 CPU 重放是延后可选项。按依赖队列续跑，不重做已通过项，不把 M0–M9 最终硬件发布作为 Goal。

你是 Sol medium 协调者、唯一 integrator 和 Git 写入者。每批取一个小包；仅有独立工作时按需并行最多 3 位 Sol medium worker，划定不重叠路径且禁止其再派生。实质代码、合同或测试批次由 Astra medium 审真实 diff、源码和证据，轻微文档由 Sol 检查；修复发现并复测。每批只写一份简短记录并更新 STATUS，不强制独立 work card、review packet 或 handoff。

日常只要求 Windows/CPU，不要求 Linux/WSL 或 Odin 3。CPU、fixture、mock、QNN CPU 不算 FSR4 HTP、设备或游戏验证；缺设备不阻塞本阶段。缺合法模型/SDK 等资产时先做全部资产无关项，必需项未实现不得 complete；无可做项时才请求最小输入。审阅通过可提交并推送当前跟踪分支；先核对远端，不覆盖他人改动。失败时保留改动和证据并定点修复，不以丢弃制造通过。仅当冻结的 H1–H4 主机验收全部通过，更新 STATUS、核对提交/远端并将 Goal 标为 complete；这不代表 M0–M9 complete。
```
