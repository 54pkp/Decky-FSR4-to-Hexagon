# 2026-09-21 / P4 ELF32/64 与大小端覆盖

- 目标与基线：基于 `7ac5068b2e7aa6837ea1ccbd885e41abc285a617`，完成上一批明确保留的 ELF32/大端合成成功路径；不扩展到真实 SDK 清单。重构测试 fixture builder，使 class 与 byte order 同时驱动 ELF header、program header、dynamic entry、`Verneed`/`Vernaux` 的布局。
- 实现与修复：ELF32/ELF64 × 小端/大端四种合成图像均核对 machine、位数、endianness、interpreter、`DT_NEEDED`、`GLIBC_*` 和 glibc 候选证据。解析器保留既有的过小 `e_ehsize` 拒绝，并新增 program-header table 不得与声明 header 重叠的检查；非重叠扩展 header 有正向回归。合成 fixture 与解析器也执行 `PT_INTERP` 必须先于 `PT_LOAD`。
- 环境与后端：Windows 11 AMD64，仓库 `.venv` Python 3.12.7；纯合成文件字节解析，无执行后端、SDK、模型或外部二进制。协调/worker 为 GPT-5.6 Sol medium，批次审阅为 GPT-6 Astra medium。

| 检查 | 结果 |
| --- | --- |
| 仅检查约定的 `sdk/`、`sdks/`、`local/{sdk,sdks,qairt,qnn}` 与 `QNN_SDK_ROOT`/`QAIRT_SDK_ROOT`/`SNPE_ROOT`/`AISW_SDK_ROOT` | 目录不存在、变量未设置；未全盘搜索，不能据此断言主机其它位置没有 SDK |
| `.venv\Scripts\python.exe -m unittest discover -s tests/abi -p "test_*.py" -v` | 退出 0；19 项通过 |
| `.venv\Scripts\python.exe -m py_compile tools/abi/inspector.py tests/abi/fixtures.py tests/abi/test_inspector.py` | 退出 0 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；172 项中 159 通过、13 skipped；9 项为基线环境故意不安装 reference 依赖，4 项为既有 Windows symlink 权限限制 |

- 审阅：Astra medium 初审确认四种布局与边界正确，无 blocking finding，并指出扩展 header 兼容性和 fixture segment 顺序残余；已改为接受不重叠的扩展 header，并让 fixture/解析器执行 `PT_INTERP` 顺序。Astra medium 对两轮受影响测试和证据定点复核通过，无剩余 actionable finding。Sol 只读审计独立核对了结构宽度与字段位置。
- 未测/限制：没有合法 QAIRT 包或真实候选库；P4 保持 `in_progress`，实际 SDK 清单步骤继续 `blocked`；多记录 `Verneed` 链尚无回归覆盖。没有加载任何 ELF，没有 QAIRT/QNN、FSR4、GPU、HTP、Odin 3 或游戏执行，设备与游戏均 `not_run`；合成四象限覆盖不证明目标 ABI 或设备兼容。
- 下一步：取得并登记合法 QAIRT 包、版本和本机支持条件后执行 P3 Windows 工具冒烟，再以实际候选库补全 P4 清单。本轮到此停止。
