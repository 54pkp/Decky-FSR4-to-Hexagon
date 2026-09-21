# 2026-09-21 / P4 多记录 Verneed 链

- 目标与基线：基于 `e943a3c319e0ae521cb2e07e7f09b0cb21fec2c4`，完成 P4 合成解析器的多记录 `DT_VERNEED` 残余覆盖；不扩展到真实 SDK 清单。fixture builder 现在可表达多个 provider、每记录多个 `Vernaux`，同时保留原单记录简写。
- 实现与边界：ELF32 小端和 ELF64 大端样例跨两个 provider 汇总、过滤并排序 `GLIBC_*` 要求；覆盖提前结束、非零尾链、记录数不符以及 provider/name 越界拒绝。审计确认相对偏移算法正确，并发现记录上限 × 每记录 aux 上限可形成约百万次迭代；新增全链最多 4096 个 auxiliary 的聚合预算及拒绝回归。
- 环境与后端：Windows 11 AMD64，仓库 `.venv` Python 3.12.7；纯合成文件字节解析，无执行后端、SDK、模型或外部二进制。协调/worker 为 GPT-5.6 Sol medium，批次审阅为 GPT-6 Astra medium。

| 检查 | 结果 |
| --- | --- |
| 仅检查约定的 `sdk/`、`sdks/`、`local/{sdk,sdks,qairt,qnn}` 与四个 SDK 环境变量 | 目录不存在、变量未设置；未全盘搜索，不能据此断言主机其它位置没有 SDK |
| `.venv\Scripts\python.exe -m unittest discover -s tests/abi -p "test_*.py" -v` | 退出 0；21 项通过 |
| `.venv\Scripts\python.exe -m py_compile tools/abi/inspector.py tests/abi/fixtures.py tests/abi/test_inspector.py` | 退出 0 |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；174 项中 161 通过、13 skipped；9 项为基线环境故意不安装 reference 依赖，4 项为既有 Windows symlink 权限限制 |

- 审阅：Astra medium 对冻结暂存差异、多记录相对偏移、聚合预算、错误链测试和以上证据审阅通过，无 actionable finding；额外内存检查确认 4096 个 auxiliary 接受、4097 个拒绝。Sol 只读审计另以四种 class/endian 矩阵验证相对基址，并触发 aggregate aux 上限修复。
- 未测/限制：没有合法 QAIRT 包或真实候选库；P4 保持 `in_progress`，实际 SDK 清单继续 `blocked`。未加载任何 ELF，没有 QAIRT/QNN、FSR4、GPU、HTP、Odin 3 或游戏执行，设备与游戏均 `not_run`；合成链测试不证明目标 ABI 或设备兼容。
- 下一步：取得并登记合法 QAIRT 包、版本和本机支持条件后执行 P3 Windows 工具冒烟，再以实际候选库补全 P4 清单。本轮到此停止。
