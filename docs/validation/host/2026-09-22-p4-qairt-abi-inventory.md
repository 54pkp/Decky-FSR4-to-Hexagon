# 2026-09-22 / P4 QAIRT ABI 候选清单

- 目标与基线：基于 `ac5faa93dde21ab51cd3f04a74d8875d0371cd10`，补完 P4 固定真实 SDK 清单，不在 Windows 加载任何 ARM64/Hexagon 文件。输入为 P3 固定 QAIRT Community 2.49.0.260730 / build `260730134355` ZIP：`2,414,977,444` bytes，SHA-256 `32de9b5b2b069aeb93ba090071e777ff464349b3296358c4d3b35040dccbd159`。
- 实现：新增确定性 `tools/abi/inventory.py`，只接收显式 archive/output；校验整包哈希、ZIP 全路径/大小写重复/symlink，从同一已打开归档把固定 allowlist 解到私有快照，逐项固定 size/SHA 并调用有界检查器。输出目录全祖先拒绝 reparse，检查前保留并持续打开临时文件，独占 hardlink 发布且拒绝覆盖。解析器补 ELF `EM_HEXAGON=164` 为 32-bit `hexagon`，但不按路径推断 HTP 或兼容性。
- 真实结果：10 项 present——3 个 Windows x86-64 PE，Android ARM64 的 HTP/System/V79 stub，OE gcc11.2 glibc ARM64 的 HTP/System/V79 stub，以及 Hexagon V79 skel；Android 与 Linux 分类来自 `DT_NEEDED`/GLIBC 二进制证据，skel 保持 `unknown_elf`。3 项只在固定包范围 missing：OE gcc9.3 V79 stub、Ubuntu gcc9.4 V79 stub、OE gcc11.2 路径的 `libcdsprpc.so`；后者可能来自 BSP/FastRPC/设备镜像，设备状态仍 unknown，V81 不替代 V79。
- 有界排除：Windows `QnnHtp.dll`、Android 与 OE gcc11.2 `libQnnHtpPrepare.so` 均超过检查器 16 MiB 上限，结构检查为 `not_run`，没有放宽上限或用文件头冒充完整报告。实际确定性收据 SHA-256 `08a8bf75b9bc6920af0cd5225f4d2440caa1b33fd1e0ca422438f4de15899460`，生成物留在忽略目录。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.abi.test_inspector tests.abi.test_inventory -v` | 退出 0；32 项通过 |
| 固定真实 ZIP 清单，两条不同输出路径 | 均退出 0；字节一致；10 present / 3 missing；同路径重跑退出 2 且未覆盖 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；224 项中 199 通过、25 skipped（可选运行库/平台或权限条件未满足） |
| `py_compile` / `git diff --check` | 退出 0 |

- 审阅：Astra medium 对冻结差异 `65d7ab1c0f2305984e4cc67586b24e86058b433e` 复审通过，无 actionable finding；独立重跑 32 项 ABI 测试和固定真实 ZIP，所得收据与本记录哈希一致。残余风险为 POSIX 分支最后一次目录复核与 hardlink 间仍可能发生目录替换；本批限定 Windows，Linux 对抗竞态未验证并继续后置。
- 未测与结论：这只是固定 QAIRT 包中所选候选的 Windows 离线结构清单，不是完整 SDK 清单。未验证 Armada OS loader/glibc、Odin 3 实际 HTP 代际、安全域签名、BSP/FastRPC、固件/权限、动态加载、QNN/HTP 执行、转换/量化、FSR4 或游戏；`device_match=unknown`、`execution=not_run`。
- 下一步：P6 使用 P3 工具与 P5 自有小图做实际 W8A8 转换/量化和 encoding 检查；本轮到此停止。
