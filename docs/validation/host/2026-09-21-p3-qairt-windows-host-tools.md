# 2026-09-21 / P3 QAIRT Windows 主机工具

- 目标与基线：基于 `f7805eb8ea9ba512e463d227abe3394dc9269277`，完成一套可追溯 QAIRT Windows 主机 SDK、独立 Python 环境和只读工具冒烟。官方 AI Hub 发行说明在本批核查时仍把 2.49.0 列为最新，未找到可验证的 2.50 官方包，因此固定 Software Center Community `2.49.0.260730`，没有混装版本。
- 包与布局：官方 URL 下载第一次在 45.7% 处以 curl 18 中断，续传后完成。ZIP 为 `2,414,977,444` bytes，SHA-256 `32de9b5b2b069aeb93ba090071e777ff464349b3296358c4d3b35040dccbd159`；12,340 项、展开 `5,982,678,461` bytes，只有 `qairt/` 顶层且未发现绝对、`..` 或反斜杠 ZIP 路径。忽略目录保留随包 `LICENSE.pdf`、`NOTICE.txt`、`NOTICE_WINDOWS.txt`、`QNN_NOTICE.txt` 等通知。`sdk.yaml` 为 QAIRT 2.49.0、build `260730134355`、flavor `[premium]`（原样记录，不作授权含义推断）；QNN release notes 标记 2.49.0 / API 2.38.0。
- 环境：系统 `python` 仍为 3.9.13，没有修改；QAIRT 使用忽略目录 `local/venvs/qairt-2.49.0.260730` 的 Python 3.12.14 AMD64。官方逐项安装脚本一度把 NumPy 漂移到 2.4.6，并带来依赖冲突；只在该 venv 内固定回官方要求的 NumPy 1.26.4 和兼容的 contourpy 1.3.3。随后 `pip --isolated check` 与官方 `check-python-dependency --dry-run` 均退出 0；可选 `qairt-visualizer 0.8.0` 未安装。一次未设置 `VIRTUAL_ENV` 的直接 dry-run 按预期拒绝，注入本批子进程环境后通过。
- 实现：`tools/qairt/probe.py` 固定来源、HTTP 元数据、包/选定文件哈希和官方 33 项 Python 依赖；只接受显式 archive、SDK、解释器和输出路径。它校验 ZIP 全部 12,340 条路径，从固定包内提取 2,698 个 Windows bin/lib 与 Python runtime 文件（`971,685,250` bytes）到私有快照，SDK 根、`PYTHONPATH`、`PATH`、三项 `--help` 和四个有界 x86-64 PE 检查均只使用该快照；展开树只做前后完整性核对。目录全祖先拒绝 reparse，Windows 发布期间固定目录身份，输出拒绝覆盖；95 MiB `QnnHtp.dll` 只做存在性/哈希检查，不绕过 16 MiB 解析上限。

| 检查 | 结果 |
| --- | --- |
| 固定真实包探针 | 退出 0；converter、quantizer、metadata help 各退出 0；收据 SHA-256 `6deb0d3b5da94d1786d91a07898f7a83ce1e85379d382dc7629ce4b1795150d1`；同路径重跑退出 2 且原收据未变 |
| `.venv\Scripts\python.exe -m unittest discover -s tests\qairt -p "test_*.py" -v` | 退出 0；15 项通过 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；213 项中 188 通过、25 skipped（可选运行库/平台或权限条件未满足） |
| QAIRT venv `pip --isolated check` / 官方 dependency dry-run | 均退出 0；33 项必需版本匹配；可选 visualizer missing |
| `py_compile` / `git diff --check` | 退出 0 |

- 审阅：Astra medium 初审指出 SDK Python 未进入快照及目录祖先/发布身份保护不足；archive runtime 修复后又以 rename＋recreate 复现错误位置发布，改为在检查前创建并持续持有发布目录内保留文件，补回归后对冻结差异 `2895cf926b526c6e6132473267dd8b9450d7282d` 复审通过，无 actionable finding。残余风险为其他文件系统语义及继承管道的后代进程可能延长超时回收。
- 未测与结论：GBK 默认输出曾因官方 help 的 U+2011 失败，探针仅给子进程注入 UTF-8 后三项 help 通过。这只证明固定入口可调用；没有执行转换、W8A8 量化、DLC 元数据导出、CPU 推理、HTP prepare/执行、Odin 3 或游戏。CPU/HTP 文件仅为离线候选，不能当作平台兼容或执行证据。
- 下一步：P4 以这套固定 SDK 生成真实候选 ABI 清单并如实登记缺失目标库；本轮到此停止，不进入 P4/P6。
