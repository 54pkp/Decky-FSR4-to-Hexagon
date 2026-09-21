# 技术研究留档 / Research archive

[项目首页 / Project home](../../README.md) · [最新路线 / Current roadmap](../roadmap/README.md) · [项目状态 / Status](../STATUS.md)

此目录保存初次研究的完整中英文文档，供查阅技术依据、上游源码差异和最初设计背景。公开首页已另外编写；当前任务以[STATUS](../STATUS.md)及[无设备](../roadmap/HOST_PREPARATION.md)/[设备](../roadmap/DEVICE_EXECUTION.md)批次为准，节点指南只提供技术条件。H/P成果见[历史索引](../roadmap/COMPLETED_HOST_BATCHES.md)。

This directory preserves the original bilingual research for technical reference. The public README is maintained separately. STATUS and the device-free/device batch plans define current work; milestone guides supply technical conditions, and dated reports preserve evidence.

| 文档 / Document | 内容 / Contents |
| --- | --- |
| [2026-09-20 可行性研究（中文）](2026-09-20-feasibility.zh-CN.md) | 四项目审计、架构、输入与 ABI、延迟/能耗边界、原始 M0–M9 规划与来源 |
| [2026-09-20 feasibility study (English)](2026-09-20-feasibility.en.md) | Full English counterpart of the original technical study |

## 来源与保留方式 / Provenance

归档来自提交 [`4bd72a710d2f07ffeb765bb5363f5ba64714d320`](https://github.com/54pkp/Decky-FSR4-to-Hexagon/commit/4bd72a710d2f07ffeb765bb5363f5ba64714d320) 中的 `README.md` 和 `README.en.md`，包含中文页对 Armada OS 名称的最新修订。技术正文保留；仅增加归档说明，并修正移动后的语言切换链接。原提交仍可用于核对原始文件。

The archive originates from `README.md` and `README.en.md` in the commit above, including the latest Armada OS naming correction in the Chinese page. Technical content is preserved. Only an archive notice and relocated language-navigation links were added or adjusted. The original files remain available in that commit. The historical English text still uses its original provisional wording; current project documentation identifies the target OS as Armada OS.

## 阅读边界 / Interpretation

- 原文的“当前”“首版”“本次”等指初次研究时的上下文，不能据此推断后续代码状态。
- 上游固定 SHA 的事实保留其版本边界；线上文档可能变化。
- 原方案中规划的路径不是已存在代码。最新拆分、工作包与数据合同见[路线索引](../roadmap/README.md)和[公共合同](../architecture/CONTRACTS.md)。
- 例如当前路线明确 M0 的平台记录与游戏选择可以分别推进：未确定游戏不阻塞 M1 平台验证。这属于实施细化，不回写成最初研究已作出的决定。
- 新发现、复现冲突或实测结果通过当前验证报告/ADR 记录，必要时在此添加勘误链接，不静默改写原始结论。

“Current,” “first release,” and similar wording inside the archived documents refer to their original research context. Pinned upstream revisions bound their claims. Proposed paths are not implemented components. New findings should be recorded in current reports or ADRs, with an erratum link here if needed, rather than silently replacing historical conclusions.

## 勘误 / Errata

目前尚无新增实机结果或归档勘误。文档归档不代表任何节点已通过硬件验收。

No new hardware results or archive errata have been added. Archiving these documents does not mark any milestone as hardware-validated.
