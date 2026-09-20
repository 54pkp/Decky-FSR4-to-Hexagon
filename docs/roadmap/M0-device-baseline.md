# M0：设备、系统与兼容栈建档

状态：**进行中；M0-A/M0-B 的主机侧 schema、采集、校验、脱敏与 fixture 已实现，M0-C/M0-D 的 Odin 3 实测和基线冻结尚未执行。** 本文仍是实施路线，不是 Odin 3 实测报告。上一节点：无；下一节点：[M1 NPU 平台闸门](M1-npu-platform.md)。

执行前阅读 [AI 实施总则](../ai/IMPLEMENTATION_GUIDE.md)、[共享合同](../architecture/CONTRACTS.md) 和 [项目状态](../STATUS.md)。历史判断保留在 [2026-09-20 可行性研究](../reference/2026-09-20-feasibility.zh-CN.md)，新的实测结论应单独记录，不改写历史证据。

## 1. 本节点交付什么

建立一份可以让下一位开发者重现环境的设备档案，回答“实际运行的是什么”，并保存任何后续修改之前的基线。

- 已知用户目标：AYN Odin 3、骁龙 8 Elite、Armada OS；系统名称按仓库最新修订确认，实际镜像版本仍待采集。
- 源码研究预期：CQ8725S / SM8750 平台族、HTP v79；这些值仍需设备与所选 QAIRT SDK 确认。
- 记录系统镜像、内核、固件、FastRPC、图形栈、Steam/Proton/FEX 和 Decky 的实际版本与位置。
- 区分 native AArch64 host、Steam 所在环境、翻译后的 guest 和 Windows PE 模块，避免以后把不兼容库装进同一个目录。
- 记录候选 DLSS SR 游戏、已有普通游戏运行情况、设置和未知项；**候选游戏未定不阻塞独立 NPU 诊断**。

非目标：不宣称 NPU 可用；不安装 QNN，不修改设备树，不刷机，不替换系统固件，不自动改变启动参数，不安装代理 DLL。

## 2. 前置材料和工作边界

需要设备所有者提供实际设备访问方式或自行运行采集命令，保留输出时间与执行环境。没有设备时，可以完成采集器、JSON Schema、匿名化示例和解析测试；所有样例必须标记 `example_only`，`device_test` 保持 `not_run`。

准备以下输入：

| 材料 | 最小要求 | 缺失时处理 |
| --- | --- | --- |
| 仓库版本 | 本仓库 commit、工作区差异 | 记录未提交修改，不假定 clean |
| 系统身份 | 镜像名称/版本/构建摘要、实际启动内核 | 没有镜像摘要时记录读取方式和未知原因 |
| 硬件身份 | device-tree model/compatible、SoC 信息 | 市场名称与内核标识分别存储 |
| 系统访问 | 普通桌面用户的 shell | 权限不足字段标 `permission_denied`，不自动 sudo |
| 图形/Steam | 已安装组件及实际可执行文件路径 | 没有 Steam 或游戏时允许平台建档先完成 |
| 配置基线 | 逐游戏启动参数、兼容工具、Armada Control 设置 | 只导出用户选定 AppID，不全盘搜集账户资料 |

采集器默认只读。输出报告是显式指定的新文件；不得修改被检查的配置。不要收集 Steam 登录令牌、完整环境变量、用户游戏存档或整份家目录。用户名/机器名/个人路径用于本地定位时保留在私有报告，提交公开仓库前脱敏。

## 3. 源码阅读顺序与永久依据

1. [Armada Odin 3 DTS，固定版本](https://github.com/armada-os/armada/blob/d38f6d9fd18b50294c14cd4081e896fc86af12db/packages/kernel/dts/cq8725s-ayn-odin3.dts)：读 `compatible`、CDSP 节点和 firmware-name，形成“预期/观察到”的对照。
2. [Armada 内核配置](https://github.com/armada-os/armada/blob/d38f6d9fd18b50294c14cd4081e896fc86af12db/packages/kernel/config/armada-kernel.config.overrides)：确认该研究快照启用 FastRPC；不能由此判断用户内核相同。
3. [Armada 固件目录](https://github.com/armada-os/armada/tree/d38f6d9fd18b50294c14cd4081e896fc86af12db/system_files/usr/lib/firmware/qcom/sm8750/ayn/odin3)：记录文件名称，不将存在文件等同于 CDSP 成功加载。
4. [Steam/Proton 配置脚本](https://github.com/armada-os/armada/blob/d38f6d9fd18b50294c14cd4081e896fc86af12db/build_files/30-install-steam-session.sh)：关注 ARM64 与 x86/FEX 路径并存，随后查用户实际选择。
5. [Valve Proton ARM64 说明](https://github.com/ValveSoftware/Proton/blob/5b89db940e0ebe3a137a6009a3589232fe084c09/README.md#L192)：ARM64 构建与 FEX 中的 x86 Steam 不是任意可替换组合。
6. [RP6 解锁项目范围](https://github.com/puzzled-pancake/rp6-npu-unlock/blob/31c701d8b0a95cde4398b6af6929cdcf75eb83e8/README.md)：只作为诊断背景，绝不将 RP6 的补丁或刷写命令放入 Odin 3 采集器。

这些链接证明研究时的源码状态。若后续更新依赖，另存新 SHA 和变更说明，不把浮动 `main` 作为复现实验输入。

## 4. 当前目录和技术选型

| 路径 | 当前状态与职责 |
| --- | --- |
| `tools/device/collect.py` | 已实现：Python 3 只读采集、超时、结构化私有报告 |
| `tools/device/profile_tools.py` | 已实现：离线 schema 校验与公开脱敏 |
| `tools/device/schema/device-profile.schema.json` | 已实现：设备档案必填、可空和证据来源约束 |
| `tools/device/fixtures/` | 已实现首批匿名综合 fixture；后续按真实缺口扩展 |
| `docs/devices/odin3-armada.md` | 待 M0-C/M0-D：经审阅的真实环境说明、兼容栈选择与未知项 |
| `artifacts/M0/<run-id>/` | 待设备运行时使用：本地原始日志、解析后 JSON、命令退出码；默认不提交大文件 |

优先 Python 标准库，读取 sysfs/procfs 和显式文件；运行外部命令用参数数组、超时和长度限制，不拼接 shell。`sysfs` 路径可因内核变化而缺失，不能把路径缺失硬编码成“不支持”。

## 5. 分批实现与每批输出

### M0-A：定义设备档案

1. 将硬件、系统、图形、NPU 基础、Steam 栈、候选游戏分为独立对象。
2. 每个观察项记录 `value`、`source`、`observed_at` 和 `status`；未知值用 `null`，不使用看似真实的默认版本号。
3. 生成唯一 `device_profile_id`。同一次基线引用同一 ID；系统镜像/内核/runtime 发生实质变化时生成新档案并记录 `supersedes`。
4. 写 JSON Schema 和 3 类样例：完整匿名样例、无 Steam 平台样例、受限权限样例。

输出：schema、字段说明和解析测试。此批只可标记 `source_review` / `host_test`。

### M0-B：实现只读采集

1. 采集 uname、os-release、libc、设备树和可读 SoC 信息；bootc 等命令仅在存在时调用。
2. 枚举 remoteproc 的 name/state/firmware，按名称识别 CDSP，不能固定 `remoteproc0`。
3. 记录 FastRPC / dma_heap 设备节点、权限、用户组和候选 Linux 库；不自行打开 DSP 会话。
4. 图形信息通过已安装的 `vulkaninfo` / `eglinfo` 读取；失败保留退出码与 stderr，不能通过安装驱动“修复采集”。
5. 只检查明确指定的 Steam、Proton、guest EXE 路径，记录 ELF/PE 架构；不由进程名称推断完整 ABI。
6. 提供预览和脱敏输出，确保 shell 参数、游戏名称和路径中的空格可以安全处理。

输出：采集器、帮助文本、命令可用性清单、原始证据与解析结果的一一对应关系。

### M0-C：在目标设备运行并审阅

1. 在用户实际登录会话运行，不在容器里采集后冒充 host。
2. 保存系统启动时间/采集时间、设备档案 ID、运行工具 commit。
3. 核对 `aarch64`、设备树 compatible 与实际镜像；未知项逐条补充来源，不靠型号推测。
4. 记录已能启动的普通游戏或图形样例；如果尚无游戏，用 `not_run` 表示，不阻塞平台分支。
5. 候选 DLSS SR 游戏优先选择已有运行记录、可重复场景且适合调试的单机游戏；这里不假定某游戏 API 已验证。

输出：设备档案、基线报告和待补材料。M1 的平台证据需求与 M3 的游戏证据需求分开标识。

### M0-D：冻结基线并交接

将公开可分享的摘要提交仓库，将含个人路径的原始记录留本地。保存原启动参数和兼容工具设置，明确本次没有修改。建立“变化后重测哪些节点”的清单：内核/固件/FastRPC/QNN 变化至少重跑 M1；GPU 驱动变化至少重跑 M2；Proton/游戏版本变化重跑 M3/M4。

这些是最早需要复核的节点。依赖组合变化后，相关下游验收也不能自动沿用；重新评估并记录 M5 画质、M6 性能和推荐 profile 的有效性，不能仅重跑 M3/M4 就继续引用旧构建的认证。

## 6. 拟议档案示例

以下只说明格式；**不是采集结果**，`example-*` 不能用于通过门槛。

```json
{
  "schema_version": "draft-0",
  "example_only": true,
  "device_profile_id": "example-odin3-baseline",
  "evidence_level": "source_review",
  "gate": "not_run",
  "hardware": {
    "market_name": "AYN Odin 3",
    "expected_soc_family": "SM8750/CQ8725S",
    "observed_compatible": null,
    "expected_htp_arch": 79,
    "observed_htp_arch": null
  },
  "os": {"expected_distribution": "Armada OS", "image_digest": null},
  "runtime_stack": {"steam_arch": null, "proton_path": null, "guest_pe_arch": null},
  "platform_inventory": {"status": "not_run", "raw_evidence": []},
  "game_candidates": [],
  "unknowns": ["installed image", "Linux QNN compatibility", "first game"]
}
```

`gate` 是本节点报告结果，字段级 `status` 只描述采集是否成功，二者不能互相代替。完整字段与类型以共享合同和实际 schema 为准。

## 7. 可立即使用的现有只读命令

下面是 **目标 Linux 的 Bash 命令**，不是 Windows PowerShell 命令，也不是已执行的记录。缺少命令时记录缺失即可。

```bash
uname -a
cat /etc/os-release
getconf GNU_LIBC_VERSION
id
for p in /sys/firmware/devicetree/base/model /sys/firmware/devicetree/base/compatible; do
  if [ -r "$p" ]; then printf '\n%s\n' "$p"; tr '\000' '\n' < "$p"; fi
done
for p in /sys/bus/soc/devices/soc0/{soc_id,family,machine,revision}; do
  if [ -r "$p" ]; then printf '\n%s\n' "$p"; cat "$p"; fi
done
for p in /sys/class/remoteproc/remoteproc*; do
  [ -d "$p" ] || continue
  printf '\n%s\n' "$p"
  for k in name state firmware; do [ ! -r "$p/$k" ] || cat "$p/$k"; done
done
ls -l /dev/fastrpc* /dev/dma_heap/* 2>/dev/null
if command -v bootc >/dev/null 2>&1; then bootc status; fi
if command -v vulkaninfo >/dev/null 2>&1; then vulkaninfo --summary; fi
```

`vulkaninfo` 会初始化图形驱动进行能力查询，应单独记录失败，不能因失败中断其它采集。设备节点通配符无匹配不等于永久不存在 NPU。

当前仓库已实现的入口如下。它们只创建建档产物，不安装或修改系统；在 Odin 3 上运行前仍需先阅读 `tools/device/README.md`，并使用一个不存在的新输出目录：

```text
python3 tools/device/collect.py --output <new-report-directory>
python3 tools/device/profile_tools.py validate <new-report-directory>/device-profile.json
python3 tools/device/profile_tools.py redact <new-report-directory>/device-profile.json --output <new-public-profile.json>
```

## 8. 验证矩阵与失败路径

| 层级 | 核查内容 | 可得出的结论 |
| --- | --- | --- |
| `source_review` | 固定 Armada DTS/构建脚本；字段出处 | 发行版源码具有相关配置 |
| `build` | 采集器打包或语法检查 | 工具可构建，不是硬件识别通过 |
| `host_test` | 缺失命令/空文件/权限错误/超时/空格路径 | 解析与错误处理可信 |
| `device_test` | 目标设备实际采集、人工对照关键字段 | 安装环境得到确认，不是 HTP 执行成功 |
| `game_test` | 普通游戏无改动基线及实际启动栈 | 指定游戏可运行；不证明 DLSS 代理或 NPU |

成功路径是“采集 → 原始证据复核 → 固定档案 ID → M1”。失败必须定位为采集工具、系统访问、驱动配置或资料缺失；不要把它们合并为“芯片锁了”。

- 没有设备：允许合并采集工具，M0 的设备 gate 保持 `not_run`，M1 仅可做工具准备。
- 无 CDSP/FastRPC：保存发现与内核信息，M1 进入平台定位，不运行 RP6 解锁脚本。
- 无 Decky：记录即可，不阻塞 NPU 平台工作。
- 无候选游戏/Steam 栈不明：M3 暂停游戏接入；M1 继续。
- 命令权限不足：保留 `permission_denied`；需要系统管理员协助时列出具体读取项，不默认以 root 重跑全部流程。

## 9. 通过门槛、暂停点与交接

M0 通过最低要求：真实目标设备档案可追溯；硬件族、镜像/内核/libc 和 GPU 基础身份明确；CDSP/FastRPC 已检查并报告结果；Steam/游戏部分明确记录已知或未知；无误报“已验证 HTP”。平台组件异常可作为 M1 的定位输入，不需要在 M0 私自修改系统。

遇到设备型号与用户描述不符、来源不明的镜像/固件、需要写设备树或刷写才能继续时暂停相关分支，提出可审阅的问题和证据。游戏未确定不属于平台暂停点。

交接按 [交接模板](../templates/handoff.md) 填写：工具 commit、`device_profile_id`、原始输出位置/摘要、运行位置（host/容器）、权限不足项、未安装组件、候选游戏、基线配置备份位置、M1 可以直接开始的动作。实际运行时创建 `docs/validation/M0/YYYY-MM-DD-<work-package>.md` 和对应 `-handoff.md`；验收记录使用 [验证报告模板](../templates/validation-report.md)，不得复制本文件的示例作为实际证据。

## 10. 可复制给下一位 AI 的任务提示词

> 请实现 M0 设备建档，先读本文件、docs/ai/IMPLEMENTATION_GUIDE.md、docs/architecture/CONTRACTS.md 和 docs/STATUS.md。先检查仓库已有实现，避免重复新建框架。范围只包括普通用户的只读采集、schema、脱敏及必要的解析测试，不安装软件、不修改系统、不刷机、不复制 DLL。为未知字段保留 null 与原因；区分 host/guest/PE 架构，不把 Armada 源码支持等同于实机支持。每批先列输出，再实现并验证，保存命令、退出码、版本和证据等级。若没有设备，交付可执行采集器和模拟输入测试，但 device_test 必须 not_run。候选游戏未定不能阻塞 M1 的平台诊断。完成后更新项目状态并按交接模板列出 M1 所需材料、已知阻塞和最小下一步，不自行进入刷机或 NPU 解锁工作。
