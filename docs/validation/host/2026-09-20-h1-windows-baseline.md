# 2026-09-20 / H1 Windows 基线可复现

- 目标与队列项：完成 H1；从只含 Git 跟踪文件的 Windows 快照运行现有 M0 unittest 和 `fixture → validate → redact → validate` 最小链路，确认不依赖私有目录。
- 基准提交、变更范围：`920a7697fa93a659008ff5b71144de4b26498fa9`；仅新增 fixture 行尾属性、本记录并更新 STATUS。初次 `git archive` 暴露 Windows `core.autocrlf=true` 会把参与固定哈希的 LF fixture 转成 CRLF；用 `.gitattributes` 固定 fixture 文本为 LF、二进制为 `-text`，未放宽校验。
- 实际模型/强度：协调者模型/强度宿主未暴露，记为 unknown；只读核查与行尾修复 worker 为 GPT-5.6 Sol / medium；批次 reviewer 为 GPT-6 Astra / medium。
- 环境、工具版本、实际后端：Windows 11 `10.0.26200`，Python `3.12.7`，pip `24.2`，`jsonschema==4.26.0`；匿名合成 fixture、离线 Python/CPU 主机工具，无设备后端。

## 检查

历史测试在临时目录中从候选 Git tree `e7aa4f40d1543ff6e36354815d61a98558a0125f` 归档展开；venv 和生成物均在仓库外。以下可复制设置用于包含本批提交的 `HEAD`，从原仓库根目录执行，随后表中 Python 命令均在 `$snapshot` 根目录执行；历史测试 tree 与冻结审阅 diff 的非测试差异仅为 STATUS 和本批证据文档。

```powershell
$run = Join-Path ([IO.Path]::GetTempPath()) ("decky-h1-" + [guid]::NewGuid().ToString("N"))
$archive = Join-Path $run "repo.zip"
$snapshot = Join-Path $run "repo"
$venv = Join-Path $run "venv"
$python = Join-Path $venv "Scripts\python.exe"
$private = Join-Path $run "private"
$public = Join-Path $run "public\device-profile.json"
New-Item -ItemType Directory -Path $run, $snapshot | Out-Null
git archive --format=zip --output=$archive HEAD
Expand-Archive -LiteralPath $archive -DestinationPath $snapshot
Set-Location $snapshot
```

| 命令或理论检查 | 退出码 / 结果 | 证据级别与 gate |
| --- | --- | --- |
| 上述 `git archive` 与 `Expand-Archive` | Git 退出 0；展开无异常；快照只含候选 tree 文件 | host_test / pass |
| `py -3.12 -m venv $venv` | 0 | host_test / pass |
| `& $python -m pip install --disable-pip-version-check -r tools/device/requirements-host.txt` | 0；安装 `jsonschema==4.26.0` | host_test / pass |
| `& $python -m unittest discover -s tests/device -v` | 0；28 项中 26 passed、2 skipped | host_test / pass；skipped 不折算为 pass |
| `& $python tools/device/collect.py --fixture-root tools/device/fixtures/comprehensive --output $private` | 0；生成 7 个 private 文件 | host_test / pass |
| `& $python tools/device/profile_tools.py validate $private/device-profile.json` | 0 | host_test / pass |
| `& $python tools/device/profile_tools.py redact $private/device-profile.json --output $public` | 0；生成 6 个 public 文件 | host_test / pass |
| `& $python tools/device/profile_tools.py validate $public` | 0 | host_test / pass |
| 归档内 `expected/evidence/path with spaces.txt` 字节/哈希检查 | 23 bytes；SHA-256 `0ec8df748cbc1a16c07738aa280a995f0da1123faac3f8f7660b0d5177223566` | host_test / pass |

本次生成的 private profile SHA-256 为 `d2c694f01c1526704417812ce004473085f0402ee32edfbfc67a6f00df0b6b6b`，public profile SHA-256 为 `477f95d4b47cd12fc6de60d46f094ffc8f9e15e2ad7df51123b780ff7b81922f`。它们含运行时间，只作为本次链路证据，不是发布资产。

- skipped：Windows 普通文件 symlink 用例按平台固定跳过；evidence symlink 用例因当前账户缺少创建符号链接权限（WinError 1314）跳过。目录 junction 和 Windows Job Object 回归实际通过。
- 审阅：GPT-6 Astra / medium 审阅完整 staged diff、相关 fixture 校验源码/tests 与临时产物；发现复现段缺少变量/cwd 且硬编码未被提交引用的 tree（P2），修复为完整 PowerShell 设置并用包含本批的 `HEAD` 后，对 tree `34fdfbb35073bbb139932d14c61ae010e2edf743` 聚焦复核通过，无剩余阻断问题。
- 未测/限制：Linux 实时采集、Odin 3、CDSP/FastRPC、QNN/HTP、真实 FSR4 权重、GPU、游戏、画质、性能、延迟和功耗均 `not_run`。本批只证明 Windows 匿名 fixture 与离线主机工具可复现。
- 下一步：H2，设计并实现资产无关的 manifest/tensor 元数据校验与合成 fixture；本批不启动。
