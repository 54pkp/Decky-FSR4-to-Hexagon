# 2026-09-21 / P9c 合成失败与关闭

- 目标与基线：基于 `e9dd4acfe4bb50b9509fedd5eb5b1d9230cbbe37`，为 H4/P9a/P9b 合成生命周期加入最小 execution-failure 与 close 事件；失败/关闭不得提交候选 history，且不把通知本身误作底层取消或静止证明。
- 实现：`execution_failed` 使用完整帧身份，只允许 executing/timed-out 的匹配 active/isolated 对象进入失败态；当前代失败失效 history，旧代迟到失败不触碰新代。失败对象继续占用 P9a 数量/逻辑 cell 预算，匹配 completion 才回收。
- 关闭：`close` 使用包含当前 generation 的 bound context 身份，拒绝旧代/错身份；active 原样转入 isolated，总资源守恒。存在 retained work 时状态为 `closing`，只允许匹配 completion 或 result-consumed 做回收，全部释放后才为 `closed`；close 后 timeout/failure/submit/reset 拒绝。pending success 仅回收，绝不提交候选 history。
- 环境：Windows AMD64；仓库 `.venv` Python 3.12.7；仅 CPU 合成生命周期，没有真实后端。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.replay.test_lifecycle -v` | 退出 0；34 项通过 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；144 项中 140 通过、4 skipped（当前 Windows 权限下普通 symlink 场景不可用） |
| `.venv\Scripts\python.exe -m py_compile tools/replay/lifecycle.py tests/replay/test_lifecycle.py` | 退出 0 |
| `git diff --check` | 退出 0；仅 Git 的 Windows LF/CRLF 工作树提示 |

- 审阅：Astra medium 对冻结 tree `8336552e97e80d9e065ec2f5b0785406f7b08bb9` 复审通过，无 actionable finding；额外只读检查覆盖五种 retained 状态、四代失败预算和 64 次 close/completion 并发。补充组合未全部固化为仓库回归测试，保留为残余风险而非设备证据。
- 未测与结论：没有真实 FSR4、QAIRT/QNN、GPU、HTP、Odin 3 或游戏执行；真实后端 error 是否同时代表 quiescence、进程级销毁、持久 close 回执及永久未完成资源的人工恢复均 unknown/not_run。本批只验证 Windows CPU 合成状态机的失败、关闭和迟到回收合同。
- 下一步：P5 在独立本地环境建立自有小型 ONNX Conv/Add/ReLU CPU 数值基准；P3 仍需合法 QAIRT 包。本轮到此停止。
