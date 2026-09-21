# 2026-09-21 / P8 FSR pass-0 CPU 对照

- 目标与基准：基于 `aad0989fc59ca4e3c489accab231cc7f48ad6d22`，只对 P7 固定公开材料中的 pass-0 子图做 Windows NumPy CPU 交叉检查；真实 P7 NPZ/graph/receipt 仍留在忽略目录。
- 输入与实现：固定上游 `puzzled-pancake/fsr4-hexagon@8c7a972ab70e5693828a856da71ce711232af463` 的 `model/sim/fsr4_sim.py`（20304 bytes，SHA-256 `e82d407f26d4cd22d7b10d25a5f5d53e236febf98414946ecba32dee1377c0fe`）对照独立标量 FKYXC 实现。工具先复核 P7 receipt 与 NPZ/graph 哈希，运行固定非零 float16 HWC `[4,6,8]` 输入，预定义最终 int8 容差为 0 LSB，并检查重复确定性、有效通道敏感性、channel-7 零权重与 poison 不变性；JSON receipt 拒绝覆盖。
- 环境：Windows AMD64；忽略的 `local/venvs/fsr-extract` 使用 Python 3.12.14、NumPy 2.2.6、jsonschema 4.26.0，实际后端仅 host CPU / NumPy；系统 Python 3.9.13 未修改。验收和实现由显式 GPT-5.6 Sol / medium worker 完成，冻结 diff 交 GPT-6 Astra / medium 审阅。

| 检查 | 结果 |
| --- | --- |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests\fsr -p "test_*.py" -v` | 退出 0；24/24 通过，含 pyc 绕过、资产并发替换快照和手算舍入/饱和回归 |
| 同一解释器运行 `pass0_check.py`，输入 P7 accepted 目录与固定 simulator | 退出 0；输出 `[2,3,16]` int8，独立/上游输出 SHA-256 同为 `a7d81ead58d6dd9ce04d6f86cfcb60fb5839a0828f21f0f99ca5872c59c5199a`，最大差 0 LSB，范围 `[-38,42]`，正负饱和计数均 0；receipt SHA-256 `4170b2824a5242b1bdfaac6bb39fbc06e23963e323e568f26bdbc5113a7769b6` |
| 同一解释器 `py_compile` 与 `pip check` | 均退出 0；无损坏依赖 |
| `local\venvs\fsr-extract\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；198 项中 188 通过、10 skipped（9 项需独立 ONNX CPU 环境，1 项普通 symlink 权限） |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；198 项中 173 通过、25 skipped（额外 15 项 P8 数值测试需独立 NumPy 环境） |
| `git diff --check` | 退出 0 |

- 审阅：Astra Medium 初审发现路径加载可能执行未校验 pyc，以及 P7 文件校验/计算/receipt 可能跨不同快照；已改为执行已散列源码字节并从已验证 NPZ/graph 字节快照计算，增加对应回归和手算标量测试。Astra 对冻结树 `d4ee6ae1597df989e0447ca2c0cf9f1234b56c5d` 定点复审通过，无剩余阻塞项。
- 未测与边界：两种实现共享同一 P7 权重来源且没有官方 golden；本批只证明固定样本上选定 pass-0 的 host CPU 数值一致。完整 passes 0–13、ONNX、QAIRT/QNN、W8A8 encoding、GPU 特征/重建、HTP、Odin 3、游戏、画质、性能、延迟、内存和功耗均 `not_run`，官方完整等价性仍 `unknown`。
- 下一批：P3 准备官方 QAIRT Windows 工具与独立环境；本轮到此停止。
