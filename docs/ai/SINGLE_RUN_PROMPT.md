# 单次小批次可复制提示

在全新 Windows 任务中选择 **GPT-5.6 Sol / medium**，复制下框全文：

```text
在 Windows 上为 Decky FSR4 to Hexagon 完成一个主机 CPU 小批次。先自举：若当前目录是 Git 仓库且 origin 规范化后等于 https://github.com/54pkp/Decky-FSR4-to-Hexagon.git，就原地使用；否则只检查 $USERPROFILE/Documents/GitHub/Decky-FSR4-to-Hexagon。目录不存在便从该 URL 克隆；存在但不是匹配仓库则停止说明。禁止全盘搜索、覆盖目录、固定预设 SHA、reset --hard、git clean 或 force-push，并保留现有修改。

进入仓库后读 AGENTS.md、docs/STATUS.md、docs/ai/MULTI_AGENT_WORKFLOW.md，检查分支、HEAD、工作树、origin 和必要证据。从 STATUS 的 H1–H4 Windows/CPU 队列按依赖选一个未完成且可验收的小批次：H1 M0 测试基线/可复现入口；H2 合成 fixture 的资产无关 manifest/tensor 元数据校验；H3 CPU 合成量化/反量化及已声明坐标的平移/重投影/reset 数值样例；H4 串联 H2/H3 的同帧单请求生命周期回放，验证帧身份、过期拒绝、超时不释放在途资源、显式完成后回收。实现、测试和简短记录缺一不可，实际 FSR4 权重 CPU 重放不属必需。不要启动 Goal 或调度，不扩到 M0–M9 最终硬件发布，不重做已通过项。

你是 Sol medium 协调者、唯一 integrator 和 Git 写入者。仅有独立工作时按需并行最多 3 位 Sol medium worker，划定不重叠路径且禁止其再派生。集成并运行相关检查；实质代码、合同或测试变更交 Astra medium 审真实 diff、源码和证据，轻微文档由 Sol 检查。完成审阅发现的相关修复、复测和必要复核。只写一份简短批次记录并更新 STATUS，不强制独立 work card、review packet 或 handoff。

日常只要求 Windows/CPU，不要求 Linux/WSL 或 Odin 3。CPU、fixture、mock、QNN CPU 不算 FSR4 HTP、设备或游戏验证；缺设备不阻塞本批。缺合法模型/SDK 等资产时先做资产无关部分，必需项未实现不得写成完成；确无可做批次时才请求最小输入并停止。审阅通过可提交并推送当前跟踪分支；先核对远端，不覆盖他人改动。失败时保留改动和证据并做可行修复，不以丢弃制造通过。更新 STATUS 后停止，不自动选择下一批；报告改动、验证、审阅、提交/推送状态和缺口。
```
