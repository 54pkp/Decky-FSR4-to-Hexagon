# 2026-09-21 / P2 外部资产登记与只读核验

- 目标与基线：基于 `045b6a258371d6ca74a63873881bed8d2b7e1a33`，新增与 H2 synthetic manifest 分离的外部资产登记合同和只读核验入口；同时修复 Windows 临时目录长路径/8.3 别名导致的 P1 测试误报。
- 产物：`tools/assets/registry.py`、简短 README、封闭合成包和 15 项资产测试。登记内容包含组件、HTTP(S) 来源、版本或 commit、平台/架构、用途、notice 状态及逐文件逻辑名、相对路径、真实 SHA-256、字节数或缺失原因。工具只检查调用方显式根目录，不扫描、不下载、不执行资产，也不在成功输出中公开本机根路径。
- 安全边界：严格拒绝未知/重复 JSON 字段、非有限数、过长整数、过深/过大 JSON、绝对/反斜杠/越界/Windows 保留路径、大小写折叠重复项、symlink/junction/reparse，以及单文件、文件数和总声明容量超限。缺失文件只能登记空哈希/空大小及非空原因；present 文件以流式 SHA-256、大小和读前后身份核对，并将已打开句柄的最终路径重新绑定到所选根目录，拒绝目录替换越界。
- 环境：Windows AMD64，显式基础解释器 Python 3.12.7；由 `tools/host/environment.py init --python <已选解释器> --venv .venv` 创建本地忽略环境，退出 0。未连接 Odin 3，未安装或运行 QAIRT/QNN，未使用真实 SDK、模型或游戏资产。

| 检查 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m unittest tests.assets.test_registry tests.host.test_environment` | 退出 0；30 项中 28 通过、2 skipped（普通 symlink 权限不可用；junction 根、嵌套逃逸、根目录替换和打开句柄越界测试通过） |
| `.venv\Scripts\python.exe -m py_compile tools/assets/registry.py tests/assets/test_registry.py` | 退出 0 |
| `.venv\Scripts\python.exe tools/assets/registry.py verify --root tools/assets/fixtures/complete --registry registry.json` | 退出 0；present=2、missing=1、`metadata_verified=true`、`execution_gate=not_run` |
| `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` | 退出 0；134 项中 130 通过、4 skipped（均为当前 Windows 权限下不能创建的 symlink 场景） |
| `git diff --check` | 退出 0；仅有 Git 的 Windows LF/CRLF 工作树提示 |

- 审阅：Astra medium 对初始冻结 tree `c4e7e95d4856c1229d9951bb82867efcf2ed6de1` 要求修改两项：非字符串 status 会泄漏 `TypeError`，以及路径预检后目录替换可能越出显式根目录。第一次修复增加显式类型检查、无 traceback 的 CLI 回归和已打开句柄最终路径复核；定点复审又指出 root 路径本身可被整体替换。现已固定 `_safe_root` 时的原始目录身份，并用句柄最终路径回退所得目录与固定身份比较；资产和 registry 的嵌套目录及 root 替换均有确定性 junction 回归。Astra medium 对冻结 tree `e698647b53e386b9bf09b3c5af564a18d6221717` 最终定点复审通过，无剩余 actionable finding；该结论不证明任意并发修改下的完整文件系统快照一致性。
- 未测与结论：本批只证明合成文件登记、元数据和内容完整性检查；FSR4 等价性、真实模型/SDK、HTP、GPU、设备、游戏、性能和画质全部 `not_run`。`metadata_verified` 不代表执行成功或许可结论。
- 下一步：P3 核对合法 QAIRT 包条件并在独立本地环境做 Windows 工具冒烟；若账户、下载或平台条件阻塞，则按规划转 P5 或 P9a。本轮到此停止。
