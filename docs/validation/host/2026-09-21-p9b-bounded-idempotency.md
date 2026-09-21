# 2026-09-21 / P9b 有界幂等保留

- 目标与基线：基于 `5478c0fc88eb0d4c523fe538b78c74f664d7ccf8`，为 H4/P9a 的消费确认和 reset 去重元数据增加固定保留窗口；窗口内维持幂等，淘汰后的迟到通知不得二次改变状态。
- 实现：每个 context 独立 FIFO 保留最近 4 个首次消费决定和 4 个首次 reset 结果；两个 namespace 互不驱逐，重复或冲突不刷新顺序。相同消费 identity + success 在窗口内 no-op，相反 success 拒绝；相同 reset request_id + expected generation 返回原 generation，参数冲突拒绝。
- 过期语义：消费记录淘汰后且没有匹配 active/isolated 请求时以 `outside the retained idempotency window` 拒绝；旧 reset 原参数因 generation 落后而拒绝。所有过期/冲突路径不提交或失效 history、不推进 generation、不释放 P9a 资源。opaque `request_id` 在有限存储下无法永久识别历史复用，因此共享合同要求其在 context 生命周期内唯一；本批不伪造无限幂等保证。
- 环境：Windows AMD64；仓库 `.venv` Python 3.12.7；仅 CPU 合成生命周期，没有真实后端。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | 退出 0；28 项通过 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；138 项中 134 通过、4 skipped（当前 Windows 权限下普通 symlink 场景不可用） |
| `.venv\Scripts\python.exe -m py_compile tools/replay/lifecycle.py tests/replay/test_lifecycle.py` | 退出 0 |
| `git diff --check` | 退出 0；仅 Git 的 Windows LF/CRLF 工作树提示 |

- 审阅：Astra medium 对冻结 tree `fad3f38921e64d3720e709cc2953d361e51b0d3c` 复审通过，无 actionable correctness finding；额外只读内存检查覆盖两个窗口持续 25+ 条记录、namespace 独立、False 重试/冲突、isolated 资源不被过期通知误释放，以及消费/reset 各 64 次并发重试。并发组合未固化为仓库回归测试，列为残余风险而非设备证据。
- 未测与结论：没有真实 FSR4、QAIRT/QNN、GPU、HTP、Odin 3 或游戏执行；进程重启后的持久幂等、正式 wire 错误码和永久 request-id tombstone 均未实现。本批只验证 Windows CPU 合成状态机的有界终态记录与拒绝原子性。
- 下一步：P9c 增加最小 execution-failure/close 事件，并验证候选 history、在途资源和迟到事件隔离；本轮到此停止。
