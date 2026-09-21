# 2026-09-21 / P9a 资源预算与背压

- 目标与基线：基于 `65c1ff2d71fec6239258549969a7639ce2cac725`，为 H4 合成生命周期的 active 与旧代 isolated 请求增加同 context 保留预算；达到上限时拒绝新 submit，不淘汰仍在途对象，匹配完成后解除背压。
- 实现：默认数量上限为 4 个 retained request；逻辑容量为每个请求的 candidate history 与 output grid cell 数之和，总上限为 `2 * spatial_reference.MAX_PIXELS`。这是稳定的主机逻辑单位，不是 CPython RAM、GPU/NPU buffer 字节。executing、pending consumption 及两者 timed-out 状态都计入；timeout 不释放，reset 只将 active 原子转移到 isolated，匹配 completion/consumption 才回收。
- 原子性：submit 在安装 active 和推进 last submitted frame 前检查数量与容量；预算拒绝不改 generation、history、active/isolated 或已提交帧。P9b 的 `_consumed`/`_reset_results` 保留范围不在本批修改。
- 环境：Windows AMD64；仓库 `.venv` Python 3.12.7；仅 CPU 合成生命周期。仓库约定的 SDK/local 目录和 QAIRT/QNN 环境变量均未配置，因此未把 P3 安装说明当作工具链完成。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | 退出 0；26 项通过 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；136 项中 132 通过、4 skipped（当前 Windows 权限下普通 symlink 场景不可用） |
| `.venv\Scripts\python.exe -m py_compile tools/replay/lifecycle.py tests/replay/test_lifecycle.py` | 退出 0 |
| `git diff --check` | 退出 0；仅 Git 的 Windows LF/CRLF 工作树提示 |

- 审阅：Astra medium 对冻结 tree `4cf24bcbedcdebf72bc55b2a650688e796543f58` 复审通过，无 actionable correctness finding；额外只读内存检查覆盖 8 种 retained 状态组合、错误身份不得回收、大整数仍按逻辑 cell 计量，以及 active + isolated 恰好达到容量上限。残余风险为瞬时实际 RAM 不受本逻辑预算约束、永久不完成会维持背压、幂等记录上限留待 P9b。
- 未测与结论：没有真实 FSR4、QAIRT/QNN、GPU、HTP、Odin 3 或游戏执行；性能、真实 buffer 字节、永久不完成任务的恢复策略仍 unknown/not_run。本批只验证 Windows CPU 合成状态机的逻辑预算、背压与回收。
- 下一步：P9b 为消费确认和 reset 幂等记录增加有界保留及过期通知语义；本轮到此停止。
