# M7：CLI、启动器与可恢复部署

> 状态：路线设计；`fsr4hex-run`、`fsr4hexctl`、`fsr4hex-daemon` 均为拟议名称，当前不是可安装命令。

先读 [AI 实施指南](../ai/IMPLEMENTATION_GUIDE.md)、[公共合同](../architecture/CONTRACTS.md)、[项目状态](../STATUS.md) 与 [归档研究](../reference/2026-09-20-feasibility.zh-CN.md)。本节点把已验证链路变成可重复操作，不把“文件放好了”当成 NPU 已工作。

## 1. 目标与非目标

目标是普通用户能够检查设备、选择 profile、部署必要适配器、保留原启动链、运行、诊断、停用和恢复。CLI 是权威控制入口，Decky 以后只调用相同能力。

优先用户级 XDG 布局、版本化运行时和按游戏配置，适应 Armada 系统镜像更新。模型、QNN runtime、DSP skel 依赖按来源与许可独立发现。

非目标：扫描后自动修改所有游戏、覆盖未知 mod、写入全局 Wine/DXVK 环境、默认 root daemon、替用户升级 Proton/FEX、自动刷固件、直接编辑 Steam 内部 VDF。

“自动启用”仅指白名单内、具体版本匹配且预检通过的配置，不是未知游戏的兼容性承诺。

## 2. 依赖与无设备工作

- 运行链路依赖 M4；安装事务、CLI 解析和 mock 服务可以与 M5/M6 并行开发。
- 发布默认推荐 profile 依赖 M5/M6；未经过它们的组合明确显示实验状态。
- M0 提供真实 Steam/Proton/FEX、容器与文件路径边界；不能硬编码 `/home/deck` 或某个用户目录。
- 无设备可在临时游戏目录做部署/中断/恢复测试；只获得 `host_test`，不等于 Armada 安装通过。
- 首轮明确支持的文件系统与用户服务环境；systemd 用户会话缺失时提供手动前台模式或清晰不支持原因。

## 3. 固定源码参考

- [hexscale-game](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/packaging/qnn/hexscale-game)：保留 `exec "$@"` 的参数边界思想，但此脚本启用的是 Vulkan/XLSR 路线。
- [qnn-wrapper](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/packaging/qnn/qnn-wrapper) 与 [安装脚本](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/packaging/qnn/install.sh)：借鉴 Linux runtime 路径和用户级部署，不直接改名发布。
- [Armada Steam 初始化](https://github.com/armada-os/armada/blob/d38f6d9fd18b50294c14cd4081e896fc86af12db/build_files/30-install-steam-session.sh)：记录现有兼容工具链，避免覆盖其逐游戏参数。
- [Proton ARM64 构建边界](https://github.com/ValveSoftware/Proton/blob/5b89db940e0ebe3a137a6009a3589232fe084c09/README.md#L192)：代理 PE ABI 与原生 daemon ABI 分开验证。
- [第三方依赖边界](https://github.com/puzzled-pancake/fsr4-hexagon/blob/8c7a972ab70e5693828a856da71ce711232af463/THIRD_PARTY.md)：本仓库的许可不能覆盖专有 SDK、权重或游戏 DLL。

## 4. 建议模块与存储布局

```text
launcher/cli/                    # 参数解析、稳定 JSON 输出、退出码
launcher/discovery/              # Steam 库、路径、架构和 model manifest
launcher/preflight/              # 环境、profile、文件冲突和 runtime 检查
launcher/deploy/                 # plan、journal、apply、recover、restore
launcher/run/                    # argv/environment、进程监督、会话凭证
packaging/user/                  # 用户服务、安装/升级/卸载入口
packaging/manifests/             # 发布文件 hash、ABI、依赖与许可清单
profiles/                       # 具体组合与对应证据
docs/validation/M7/              # 日期-工作包.md 与 -handoff.md
```

拟议用户路径：配置位于 `$XDG_CONFIG_HOME/fsr4hex`，运行时和模型索引位于 `$XDG_DATA_HOME/fsr4hex`，事务/备份位于 `$XDG_STATE_HOME/fsr4hex`，socket/锁/凭证位于 `$XDG_RUNTIME_DIR/fsr4hex`。

缺省值按 XDG 约定处理并文档化；runtime 目录必须属于正确登录用户且权限受限。不要在 `/tmp` 使用可被其它用户替换的固定 socket 或凭证名。

## 5. 分批实现路线

### M7.1 CLI 合同与只读发现

1. 决定可维护的实现语言，锁定工具版本；不要为了启动器引入大体积推理依赖。
2. 先实现 `doctor`、`status`、`profiles list`、`models list`、`plan`；统一机器可读 JSON 与人类可读文本。
3. 将发现值、用户指定值与已验证 profile 区分，冲突时给具体字段；不能仅按 AppID 猜 DLL 路径。
4. 只读发现 Steam library、实际 EXE、compatdata、启动链与符号链接；路径不确定时停止部署，但可输出诊断。
5. 预检同时验证 adapter ABI、图形 API、运行时版本、模型哈希与 shape、服务权限和冲突文件。

配置优先级遵循公共合同：本次显式 CLI → 每游戏设置 → 全局偏好 → 保守默认。输出每个实际生效值及来源；配置优先级不能越过后端 capability，默认禁用。

输出 CLI schema 与只读 golden fixtures；日志隐藏会话凭证，不收集无关用户文件或账号数据。

### M7.2 事务部署与恢复

1. `plan` 解析目标绝对路径，确认每个写入目标位于选定游戏/本项目目录；记录 symlink 策略，不跟随未知跳转写文件。
2. 为每个 AppID 与实际安装路径获取互斥锁，生成不可变 plan：原始哈希/权限、备份路径、目标哈希、profile revision。
3. 先生成可验证备份，再写 journal；临时文件与目标同文件系统，flush 后原子 rename，journal 每一步可恢复。
4. 安装前再次比较哈希，防止 plan 到 apply 之间游戏更新或其它 mod 改写文件。
5. 已存在且不归项目拥有的 `dxgi.dll` / NGX DLL / 配置不可直接覆盖；输出冲突与可选适配工作包。
6. 完成后重读文件并验证哈希，再将事务标记 committed；断电或进程被杀后可扫描未完成 journal。
7. restore 先检查当前文件仍匹配“项目安装版本”。原来不存在的文件只删除本项目新增版本；原来存在的文件先校验备份，再原子恢复原内容和权限。当前文件已变化或备份校验失败时保留现状与备份并报告冲突，不强制覆盖或删除。恢复操作同样记入可恢复 journal。

事务状态建议为 `planned → backed_up → applying → committed`，另有 `recovering`、`restored`、`conflict`。这是部署状态，与公共 gate 状态分开。

### M7.3 启动包装与服务生命周期

1. `--` 后保留原命令的 argv 数组，直接 exec/spawn；禁止拼接 shell 字符串、`eval` 或 `sh -c` 执行未知参数。
2. 启动选定且锁定的原生 AArch64 daemon，等待有期限的协议握手；端口存在不等于正确服务就绪。
3. 向游戏传递最少配置与会话凭证，验证容器可见性；只监听本地，服务身份和版本不匹配则拒绝。
4. 增补当前进程环境，合并既有 `WINEDLLOVERRIDES` 等条目；冲突需明确报错，不能覆盖 Armada/其它 mod 参数。
5. 对游戏退出码与信号做明确传递；设计多进程 launcher 和父进程先退场情况，不能看见 Steam 启动器退出便删 adapter。
6. 退出恢复与运行中替换分离；已有映射 DLL、活动会话或另一个游戏使用的 runtime 不可直接删掉。
7. 创建前预检失败时按配置决定原样启动或返回失败；游戏已经启用代理后仅使用 M4 已验证的故障策略。

全局环境变量仅能选择 wrapper 已实现的功能；不要写系统级 `LD_PRELOAD`、永久 layer 或 GPU spoof。Windows PE DLL 不由 `LD_PRELOAD` 通用替换。

### M7.4 升级、卸载与发布包

运行时采用版本目录；新版本先安装、验证再切换引用。活跃会话继续使用已锁定版本，升级不热换模型/history。

卸载顺序：禁止新会话 → 等待或明确处理活动游戏 → 恢复项目部署 → 停用项目用户服务 → 删除项目拥有且未修改文件。保留冲突报告和必要恢复备份。

发布清单区分本项目代码、第三方开源代码、用户自行提供模型/SDK/runtime/skel。许可未确认的资产不入包，提供来源、版本与校验步骤；不从用户机器复制专有库上传仓库。

## 6. 拟议接口与 profile

以下仅描述未来 CLI，不能在当前仓库执行得到功能：

```text
fsr4hexctl doctor --json
fsr4hexctl plan --appid <id> --profile <id> --json
fsr4hexctl apply --plan <plan-id> --json
fsr4hexctl restore --deployment <deployment-id> --json
fsr4hexctl recover --transaction <transaction-id> --json
fsr4hex-run --profile <verified-profile> -- <original-command> [args...]
```

拟议 profile 至少含 `appid`、实际安装标识、游戏构建/EXE hash、API、PE ABI、Proton/FEX 约束、代理加载名、模型清单、已验证 mode、环境增量、部署计划与证据链接。

`profile_revision`、`deployment_id` 和版本清单必须进入会话日志，关联公共 `device_profile_id`、`model_manifest_id`、`service_instance_id`、`session_id`。配置 `enabled` 与运行状态 `active`、实际 backend 分开；服务重启换新实例 ID。

控制 API 返回 `request_id`、操作状态、稳定错误码、可恢复性和实际配置 revision。不要把写偏好成功作为 daemon 执行成功。

首版 Steam Launch Options 可给出 `fsr4hex-run --profile auto -- %command%` 的待复制文本；如何保留原有复杂包装链必须实测，不提供覆盖原字段的一刀切操作。

## 7. 错误与回滚矩阵

| 场景 | 行为 | 证据 |
| --- | --- | --- |
| 磁盘满、备份失败 | 在写游戏文件前停止 | journal 与未变化哈希 |
| 写一半被杀 | 下次从 journal 恢复 | 每个阶段故障注入 |
| 游戏更新改写 DLL | 拒绝旧 plan，重新检测 | hash mismatch、保留新文件 |
| 其它 mod 占用入口 | 不覆盖，输出冲突路径 | 已有文件 hash 与来源未知标记 |
| daemon / model 不匹配 | 拒绝启用该会话 | 实际版本与期望版本 |
| 断连或启动超时 | 有界失败，按既定策略退出/回退 | 无无限等待和假在线 |
| 同时启动两款游戏 | 单会话 MVP 明确拒绝第二个运行会话；声明支持并发后才采用独立会话和共享运行时引用计数 | 配置锁保持独立，不串写 profile、不误停止服务 |
| 恢复时项目文件已被改 | 保留双方并报冲突 | 可人工审阅的恢复计划 |
| 用户服务不可用 | 前台模式或明确 blocked | 不隐式改用 root |

## 8. 验收门槛

- `source_review`：所有写入有所有权和路径边界；argv 未经 shell 重解析；包资产来源完整。
- `build` / `host_test`：空格、中文、引号、美元符号、长路径、symlink、只读目录、多库、多实例测试通过。
- 事务测试覆盖计划后变更、任一步骤中断、重复 apply/restore、磁盘不足和并发；重复命令幂等且不丢备份。
- `device_test`：普通用户安装/升级/停用/卸载；Armada 更新或重启后检测准确；模型缺失能解释原因。
- `game_test`：原命令可运行，启用后真实 HTP 有证据；停用/恢复后原游戏与既有启动参数仍可使用。
- 没有实际设备时后两项保持 `not_run`；每个 gate 限 `not_run` / `pass` / `fail` / `blocked`。
- M7 完成不自动发布“推荐模式”；该标记必须引用 M5/M6 同组合证据。

## 9. 交接与 AI 提示词

交接包含 CLI/API schema、退出码、示例 plan/journal、XDG 布局、路径/所有权规则、升级矩阵、未解决冲突、实际包清单及 [验证报告](../templates/validation-report.md)。报告写入 `docs/validation/M7/YYYY-MM-DD-<work-package>.md`，交接为同名 `-handoff.md`。M8 必须复用这些操作，不能另写第二套安装器。

```text
实施 M7 的一个批次。先读 AI 指南、公共合同、本路线及 M4/M5/M6 实际证据。
先做只读 plan 与用户级临时目录测试，再实现带哈希备份和 journal 的部署。
fsr4hex-run 保留原 argv，禁止 eval/sh -c 拼接；保留 Armada 与其它 mod 参数。
每次写入校验路径、文件所有权和 plan 前置哈希；冲突时保留双方并报错。
不要修改 Steam VDF、全局环境或捆绑未确认许可的 SDK/模型/固件。
没有设备只完成 host_test；输出变更、故障注入结果、恢复方法与未测清单。
```
