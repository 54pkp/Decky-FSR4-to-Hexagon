# 2026-09-21 / P4 合成 PE/ELF 离线检查

- 目标与基线：基于 `fa3a247b958d58691e6e87e4e78ed6d804433432`，交付 P4 的自有合成解析部分；新增标准库只读 PE/ELF 检查器、合成 fixture builder 与错误输入回归，不加载二进制、不检查真实 SDK 库。
- 实现：报告格式、machine、位数及调用方显式 SDK 版本；ELF 通过有界 program/dynamic table、虚拟地址到单一 `PT_LOAD` 映射和 `DT_VERNEED` 链解析 interpreter、`DT_NEEDED` 与 `GLIBC_*` 要求。Android/glibc 候选只采用结构化二进制证据；AArch64、路径名或原始 `GLIBC_` 字节不构成分类证明，冲突证据保持 `unknown_elf`。
- 环境与实际后端：Windows 11 AMD64，仓库 `.venv` Python 3.12.7；纯文件字节解析，无运行后端、SDK、模型或外部资产。协调/worker 为 GPT-5.6 Sol medium，批次审阅为 GPT-6 Astra medium。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest discover -s tests/abi -p "test_*.py" -v` | 退出 0；14 项通过 |
| `.venv\Scripts\python.exe -m py_compile tools/abi/inspector.py tests/abi/fixtures.py tests/abi/test_inspector.py` | 退出 0 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | 退出 0；167 项中 154 通过、13 skipped；9 项为基线环境故意不安装 reference 依赖，4 项为既有 Windows symlink 权限限制 |

- 审阅：Astra medium 初审发现 `PT_NULL` 的未使用字段被通用 segment 规则误拒，以及 `DT_VERNEED.vn_file` 越界未校验；已按 segment 类型处理并校验版本依赖提供者字符串，增加对应回归。Astra medium 对受影响实现和测试定点复核通过，无剩余 actionable finding。协调者另收紧 glibc linker 证据并消除重复大字符串表复制。
- 未测/限制：没有合法 QAIRT 包或真实候选库，P4 保持 `in_progress`，实际 SDK 清单步骤为 `blocked`；ELF32/大端成功路径尚无回归覆盖。没有执行 PE/ELF、QAIRT/QNN、FSR4、GPU、HTP、Odin 3 或游戏，设备与游戏均 `not_run`。合成解析不证明 Android、Linux glibc、Armada OS 或目标设备兼容。
- 下一步：用户提供或在约定本地位置放置合法 QAIRT 包及其版本/来源后执行 P3 Windows 工具冒烟；随后把实际候选库交给本检查器，补全 P4 清单。本轮到此停止。
