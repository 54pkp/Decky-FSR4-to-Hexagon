# 2026-09-20 / H3 affine int8 数值参考

- 目标与队列项：完成 H3 的量化/反量化子批次；用小尺寸合成数据固定 affine int8 的舍入、饱和、反量化和非饱和误差界。平移、重投影与 reset 尚未实现，因此 H3 仅为 `in_progress`。
- 基准提交、变更范围：`8263a246b290a3111c19f03fbc9e74d292a6a6d1`；新增 `tools/model/numeric_reference.py`、固定数值 fixture 和 `tests/model/test_numeric_reference.py`，扩展 fixture LF/二进制 Git 属性并更新 STATUS。不修改 H2 manifest schema、生产模型合同或设备 ABI。
- 实际模型/强度：协调者模型/强度宿主未暴露，记为 unknown；实现与只读数值核查 worker 为 GPT-5.6 Sol / medium；批次 reviewer 为 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows 11 `10.0.26200`，Python `3.12.7`；Python 标准库、IEEE 754 binary64、离线 CPU 合成数据，无模型执行后端。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `python -m unittest tests/model/test_numeric_reference.py -v` | 0；16/16 passed | host_test / pass |
| `python -m unittest discover -s tests/model -p "test_*.py" -v` | 0；36/36 passed | host_test / pass |
| `python -m unittest discover -s tests/device -v` | 0；28 项中 26 passed、2 skipped | host_test / pass；skipped 不折算为 pass |
| `python tools/model/numeric_reference.py verify --fixture tools/model/fixtures/quantization-reference.json` | 0；固定 fixture 通过 | host_test / pass |
| `python -m py_compile tools/model/numeric_reference.py tests/model/test_numeric_reference.py` | 0 | build / pass |
| `git diff --check` | 0 | source_review / pass |
| 从候选 Git tree `4aac317e699446271baf5950779b3c286fc771ed` 执行 `git archive` 并读取 fixture entry | 0；1235 bytes，SHA-256 与下述记录一致；`text=set,eol=lf` | host_test / pass |
| 手算固定预期 | `scale=0.25,zp=-3`：`-0.625→-5.5→q=-6→-0.75`；`0.875→0.5→q=1→1.0`；`-40/33` 饱和为 `-128/127`；`0.3125→q=-2→0.25`，误差 `0.0625≤0.125` | source_review / pass |

约定为 `q=clamp(round_half_away_from_zero(x/scale+zero_point),-128,127)`、`dequant=(q-zero_point)*scale`。比较绝对容差固定为 `1e-12`；非饱和最大误差固定为 `scale/2=0.125`，饱和样例明确不套用该误差界。fixture SHA-256 为 `49e4c231c33b24b446e4f92d96a00f22b1689c788ae770e447ef9322b167d41f`（1235 bytes）。这是 host synthetic zero-point 约定，不是未经 SDK 证明的 QNN offset 转换。

- skipped：既有 device 回归中，Windows 普通文件 symlink 用例按平台固定跳过；evidence symlink 用例因当前账户缺少创建符号链接权限（WinError 1314）跳过。
- 审阅：GPT-6 Astra / medium 审阅完整 staged diff、手算预期、误差边界和测试证据；发现 tie 覆盖错误复用 `1e-12` 比较容差，邻近非 tie 可冒充精确边界（P2）。改为精确 binary64 half-tie 判定并增加邻近值拒绝回归后，对 tree `cf904d9e0717986c6c8df3f5f23cc7e888e49cc1` 聚焦复核通过，无剩余 findings。
- 未测/限制：H3 的平移、重投影、MV 方向/坐标和 reset 仍未实现。Linux、Odin 3、GPU、QNN/HTP、真实 FSR4、游戏、完整模型数值等价、画质、性能、延迟和功耗均 `not_run`；本批只验证选定的合成 affine int8 CPU 算子。
- 下一步：继续 H3，固定坐标原点与 MV 方向，实现小尺寸平移、重投影和 reset 样例；本批不启动。
