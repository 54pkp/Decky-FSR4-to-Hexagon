# 2026-09-20 / H3 空间重投影与 reset 参考

- 目标与队列项：完成 H3 剩余空间子批次；用小尺寸合成网格固定坐标原点、轴方向、forward 平移、backward MV 重投影、越界填充与 reset 零 history 采样。结合上一批 affine int8 记录后，H3 主机范围完成。
- 基准提交、变更范围：`504ca5e5d3e913d107c279d72a91fc185d46026a`；新增 `tools/model/spatial_reference.py`、固定 fixture 和 `tests/model/test_spatial_reference.py`，并更新 STATUS。不修改生产帧协议、游戏适配或设备 ABI。
- 实际模型/强度：协调者模型/强度宿主未暴露，记为 unknown；实现与只读坐标核查 worker 为 GPT-5.6 Sol / medium；批次 reviewer 为 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows 11 `10.0.26200`，Python `3.12.7`；Python 标准库、离线 CPU 合成整数网格，无模型、图形或设备执行后端。

## 检查

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| `python -m unittest tests.model.test_spatial_reference -v` | 0；13/13 passed | host_test / pass |
| `python -m unittest discover -s tests/model -p "test_*.py" -v` | 0；49/49 passed | host_test / pass |
| `python -m unittest discover -s tests/device -v` | 0；28 项中 26 passed、2 skipped | host_test / pass；skipped 不折算为 pass |
| `python tools/model/spatial_reference.py verify --fixture tools/model/fixtures/spatial-reference.json` | 0；固定 fixture 通过 | host_test / pass |
| `python -m py_compile tools/model/spatial_reference.py tests/model/test_spatial_reference.py` | 0 | build / pass |
| `git diff --check` | 0 | source_review / pass |
| 从候选 Git tree `850a139b72997dd178c8e0d7be7a4a990b913311` 执行 `git archive` 并读取 fixture entry | 0；1428 bytes，SHA-256 与下述记录一致；`text=set,eol=lf` | host_test / pass |
| 手算固定预期 | `src=[[1..4],[5..8],[9..12]]`，forward shift `(+1,+1)` 与逐目标 backward MV `(-1,-1)` 均得 `[[N,N,N,N],[N,1,2,3],[N,5,6,7]]`；reset 得全 `N` | source_review / pass；整数精确比较，容差为 0 |

约定数组索引为 `[y][x]`，左上原点、`+x` 向右、`+y` 向下。平移为 `dst(x+shift_x,y+shift_y)=src(x,y)`；重投影为 destination gather：`dst(x,y)=history(x+mv_x,y+mv_y)`，所以内容右下移动 `(1,1)` 对应 MV `(-1,-1)`。采样仅接受整数，不插值、不 clamp，越界为 JSON `null`。reset 在确定输出尺寸后不验证或读取 history，并输出全 `null`；这不等于 H4 的 generation、在途隔离或幂等 reset 生命周期已实现。fixture SHA-256 为 `5f2ca21e74ed699ec06820a6f671440e26a3fab7bc8791c8fd40f5ac4650097f`（1428 bytes）。

- skipped：既有 device 回归中，Windows 普通文件 symlink 用例按平台固定跳过；evidence symlink 用例因当前账户缺少创建符号链接权限（WinError 1314）跳过。
- 审阅：GPT-6 Astra / medium 审阅完整 staged diff、坐标/MV 方向、独立固定预期、reset 零采样与测试证据；对 tree `171317b51bb9d07b8548855984300dc700df2766` 直接通过，无 correctness findings，并确认本批与上一批量化记录共同支持 H3 主机范围 `complete`。
- 未测/限制：这是选定的 host synthetic 内部约定，不冻结任何游戏原生 MV、jitter、深度、曝光或适配器映射。Linux、Odin 3、GPU、QNN/HTP、真实 FSR4、游戏、完整模型数值等价、画质、性能、延迟和功耗均 `not_run`。
- 下一步：H4 同帧生命周期回放；使用 H2 合成 manifest 身份与 H3 参考算子，先实现同 context 单请求在途和完整帧身份核对；本批不启动。
