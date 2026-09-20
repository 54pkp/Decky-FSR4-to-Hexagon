# 项目状态

更新日期：2026-09-20。当前变化为文档整理和实施路线补充，不包含运行时实现或设备测试。

[首页](../README.md) · [路线图](roadmap/README.md) · [证据定义](ai/IMPLEMENTATION_GUIDE.md)

## 已交付

- 对四个上游仓库的初始源码研究与可行性方案，保留[中英文归档](reference/README.md)。
- 面向外部访客的中英文 README。
- M0–M9 十个节点的实施指南、跨模块合同草案、AI 接续指南与报告模板。

## 实现与验证状态

`not_started` 是节点实现进度；`not_run` 是该类检查尚未运行。这里的文档完成不改变这些状态。

| 节点 | 技术路线文档 | 实现进度 | 主机验证 | 设备验证 | 游戏验证 | 实际验收报告 |
| --- | --- | --- | --- | --- | --- | --- |
| [M0](roadmap/M0-device-baseline.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M1](roadmap/M1-npu-platform.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M2](roadmap/M2-fsr4-port.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M3](roadmap/M3-game-probe.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M4](roadmap/M4-end-to-end.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M5](roadmap/M5-temporal-quality.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M6](roadmap/M6-performance.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M7](roadmap/M7-launcher-packaging.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M8](roadmap/M8-decky-integration.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |
| [M9](roadmap/M9-compatibility.md) | 初版完成 | not_started | not_run | not_run | not_run | 尚无 |

某节点不涉及某类验证时，在真实报告中注明“不适用及原因”，不要把不适用写成通过。源码研究与本次 Markdown 检查不填入此处的运行时验收栏。

## 已知目标与待确认输入

| 项目 | 当前信息 |
| --- | --- |
| 设备 | AYN Odin 3，来自项目目标指定，尚未现场采集 |
| SoC | Snapdragon 8 Elite；源码参考为 SM8750/CQ8725S 平台族，实际识别和 QNN 枚举待查 |
| 系统 | Armada OS，镜像版本、内核、固件运行状态待查 |
| NPU | 预期 v79，真实 Linux QNN 图执行未验证 |
| Steam/Proton/FEX/Decky | 实际版本与加载架构待查 |
| 首个游戏 | 未确定；不能预先发布兼容性结论 |
| 模型/SDK | 来源、版本和本地可用资产需实施时登记；未随仓库分发 |

下一步建议为 **M0 的只读采集与基线记录**，之后按记录推进 M1。现在没有运行时失败证据，因此不把“尚未测试”写成“已失败”或“设备不支持”。

## 更新规则

每完成一个工作包，添加真实报告链接、源码提交和最后验证日期，再更新对应状态。保留失败和未运行项目，不能只留下最终绿色结果。若环境/模型/API 改变，旧报告仍可保留，但适用范围不能自动扩大。

节点 `complete` 要满足其全部必需门槛；只做了主机部分时使用 `in_progress`。开始实施后被缺失环境或外部条件阻断，才写 `blocked`，并指出可继续的独立工作。
