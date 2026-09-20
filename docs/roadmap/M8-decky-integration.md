# M8：Steam 与 Decky 控制界面

> 状态：路线设计；当前仓库没有可安装 Decky 插件。本文的组件、调用名、页面与工作流均为拟议实现。

先读 [AI 实施指南](../ai/IMPLEMENTATION_GUIDE.md)、[公共合同](../architecture/CONTRACTS.md)、[M7](M7-launcher-packaging.md) 和 [项目状态](../STATUS.md)。Decky 是可选管理界面，运行链路与恢复能力必须在没有 UI 时成立。

## 1. 目标与非目标

目标是用手柄完成游戏配置选择、预检、查看具体部署计划、执行已授权操作、查看真实运行状态、导出诊断和恢复。操作效果与 M7 CLI 一致。

UI 需要解释服务、模型、平台与游戏接入各自状态；“已保存启用偏好”“服务在线”“HTP 正在执行”是不同事实。

非目标：在 Python/JS 搬运每帧纹理或执行 QNN、重新实现安装/回滚算法、接管所有 Steam 启动项、提供任意 shell/root 命令接口。

本节点不假定某个 `currentAppId` 全局变量或内部 Steam API 永久存在；必须在实际 Decky/Steam 版本检验来源并封装宿主适配器。

## 2. 依赖与无设备工作

- 核心依赖 M7 稳定的 CLI/control API 与可恢复部署；M8 不应修补 M7 没有的原子性。
- 默认推荐模式需要同组合 M6 结论；实验 profile 在 UI 中明确标记，不因面板可显示就晋级。
- M0 提供 Decky Loader、Steam UI、Armada 镜像和运行用户信息；版本变化需要重复宿主适配验证。
- 无设备可实现 mock 控制端、类型校验、状态机和竞态测试；标 `host_test`，不能声称手柄/宿主通过。
- 后端发现服务必须绑定当前用户会话，不扫描所有 `/run/user/*` 后随便选第一个 socket。

## 3. 固定源码参考

- [fork Decky 前端](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/decky/src/index.tsx)：参考 callable 与面板组织，其 stored setting 不代表硬件功率已改变。
- [fork Decky 后端](https://github.com/54pkp/hexscale/blob/8fed58387dcd5b417910b71f15b12d3aa1e509fa/decky/main.py)：只作控制骨架参考；不要继承宽泛用户 socket 搜索或保存偏好后直接返回执行成功的行为。
- [上游 Decky 后端](https://github.com/drewano/hexscale/blob/29dc6a67c764513b3e85beb9cf548bce133a1899/decky/main.py)：控制 daemon 并不等于为游戏部署 DLSS 代理。
- [Armada Steam 配置](https://github.com/armada-os/armada/blob/d38f6d9fd18b50294c14cd4081e896fc86af12db/build_files/30-install-steam-session.sh)：避免覆盖实际兼容工具链。

实施时另行读取安装版本的 Decky 官方模板/API 与 Steam 宿主能力，锁定依赖版本和来源 SHA。此处不宣称当前有稳定“当前游戏 ID”接口。

## 4. 建议模块与 UI 状态

```text
decky/src/host/SteamHostAdapter.ts  # 版本相关游戏上下文、启动项能力
decky/src/api/control.ts           # M7 类型合同、请求 ID、超时与错误
decky/src/state/gameState.ts       # 按 AppID 的状态，不用单个全局状态
decky/src/components/              # 设备状态、游戏卡、部署计划、诊断
decky/src/index.tsx                # 插件入口、清理与错误边界
decky/main.py                     # 受限控制桥接，绑定正确登录用户的服务
decky/tests/fixtures/              # 模拟离线/竞态/版本不兼容响应
docs/validation/M8/                # 日期-工作包.md 与 -handoff.md
```

建议页面为“设备”“当前/所选游戏”“诊断”。设备页分项展示 driver、FastRPC、QNN provider、模型、GPU 与服务；游戏页展示 profile 匹配、部署 revision、待重启修改及实际后端。

用户偏好 `enabled` 与观察状态 `active` 分开保存。期望启用但无 Evaluate 调用时显示“已配置，等待游戏接入”，不能显示“正在 NPU 超分”。

## 5. 分批实现路线

### M8.1 宿主最小探针

1. 在实际 Decky 环境创建最小可加载插件，记录 Loader/API/Steam UI 版本、运行 UID 与架构。
2. 验证 callable 通信和 unload 清理，明确前端、插件后端、用户 daemon 三者权限边界。
3. 在只读模式确认游戏上下文来源：当前运行游戏、所选详情页游戏、手动选择分别定义。
4. 自动识别不可用时回退到明确显示 AppID 的手动选择；不得从窗口标题猜身份后进行写操作。
5. 确认同一宿主是否支持已文档化的启动项读写；没有稳定能力时保留复制 Launch Options 文本的路径。

输出 `host-capabilities` 记录；没有证据的能力标 `unsupported` 或 `unknown`，不调用臆造 Steam API。

### M8.2 只读状态和游戏卡片

1. 建立类型化响应，字段缺失显示未知；协议版本错误给明确消息。
2. 状态只来自 M7/control API：服务版本、模型清单、实际后端、服务实例、会话、`htp_execute_successes`、`fresh_results`、`output_writebacks`、`cached_redisplays` 与失败数。
3. p50/p95/p99 的统计窗口与范围必须显示；阶段耗时不能标成输入延迟。
4. 初次载入、断线、重连、daemon 重启、未开始游戏状态均独立建模；`service_instance_id` 变化时丢弃旧会话状态和统计窗口，不把计数归零误报为负速率。
5. 状态轮询设置有限频率、超时和退避，隐藏/卸载后取消；不为 UI 刷新阻塞推理线程。

### M8.3 请求身份、竞态和操作状态机

每个请求在点击时捕获不可变 `appid`、profile revision 与 `request_id`，传给后端并回显。不能在异步完成时重新读取“当前游戏”来决定写入对象。

1. 按 AppID 管理请求队列和 loading；A 游戏请求返回时只能更新 A 的缓存。
2. A→B→A 快速切换时按 request ID/revision 丢弃过期响应，不以到达顺序覆盖新状态。
3. 后端再次校验 AppID、安装路径与 profile 所属关系；前端传入任意路径不得直接写盘。
4. 对写操作使用 M7 plan ID、配置 revision、幂等键；重复点击或网络重试不产生两份部署。
5. UI 不乐观地把开关染成成功：区分 submitting、saved、applied、requires_restart、failed。
6. 活动游戏只能使用运行时明确支持的安全热更新；否则保存下次启动配置，不热换 DLL/模型/history。

### M8.4 具体部署、启动参数与恢复

显示 M7 返回的具体文件变化、备份位置、匹配 profile 与参数增量，让用户能理解本次动作。用户已经授权的安装/启用/恢复范围内直接完成，不添加循环确认。

需要额外决定时先准备可审阅的 plan，说明真实缺项；不能用笼统“安全考虑”把所有动作变成确认弹窗。

首版优先显示可复制的启动包装文本，并清楚保留已有 Armada Control、环境变量与其它 mod 包装链。已有参数含复杂 shell 语义时只呈现修改建议，不能自行拆解后覆盖。

不擅自改 Steam VDF。以后若实现宿主支持的写入能力，要独立适配、读取原值、记录 revision、检查并发变化、可恢复且遵从当前授权范围；不能由前端直接写文件。

“停用”只撤销本项目配置或调用 M7 restore；活动会话需显示何时生效。“卸载插件”不等于已经恢复游戏 DLL，提供明确的 CLI 恢复入口。

### M8.5 诊断导出与宿主失效

诊断包含版本、profile ID、device/model ID、会话 ID、错误码、计数摘要和部署状态；默认脱敏用户名、完整游戏路径和凭证，不打包原始游戏纹理。

插件 reload/unload 只取消 UI 请求和订阅，不终止游戏或共享 daemon。Decky 崩溃后用户仍可用 M7 CLI 读取状态、停用和恢复。

## 6. 拟议接口示例

下列名称为项目内部候选，不是 Decky/Steam 官方固定接口：

```ts
type GameRequest = {
  request_id: string;
  appid: string;
  profile_revision: string | null;
};
type MutationRequest = GameRequest & {
  plan_id: string;
  expected_revision: string;
  idempotency_key: string;
};
// getGameStatus(request), planEnable(request), applyPlan(request), restore(request)
```

响应必须回显 `request_id` / `appid` 并携带 revision、实际操作结果、稳定错误码。会话遥测沿用公共 `service_instance_id` / `session_id` / `context_id` / `frame_id` / `history_generation`，不在 Decky 端自增帧号；长整数按字符串传递，不能隐式转为 JS Number。

后端仅暴露白名单方法，校验长度、类型、profile 是否已知和目标用户。若调用 CLI，使用 argv 列表与结构化输入输出，拒绝 shell 字符串和任意 root 透传。

## 7. 失败与回滚矩阵

| 场景 | 正确表现 | 验证方式 |
| --- | --- | --- |
| 快速切换游戏时旧响应到达 | 不修改新游戏，缓存按 AppID 隔离 | 延迟/乱序 mock |
| 当前游戏识别失效 | 显示未知并允许明确选择 | 宿主能力禁用 |
| 保存配置但 daemon 拒绝 | 显示 saved 与 failed 差异 | 注入后端失败 |
| Decky 后端权限较高 | 不借此写其它用户目录或任意命令 | UID/目标校验测试 |
| daemon 离线或协议不匹配 | 显示实际状态、退避重试 | 杀进程/错误版本 |
| 游戏运行中改模型 | 标下次启动，不污染当前 history | 活跃 context 验证 |
| UI 重载/崩溃 | 游戏推理继续，CLI 可恢复 | 宿主卸载实验 |
| Steam/Armada 更新 | 受影响宿主能力禁用，不破坏旧配置 | capability mismatch |

## 8. 验收门槛

- `source_review`：只有受限控制操作；前端/后端不处理帧载荷；没有任意 shell 或写 VDF 捷径。
- `build` / `host_test`：类型、错误状态、重试、取消、重复操作、AppID/revision 竞态覆盖通过。
- `device_test`：目标 Armada/Decky/Steam 组合加载、卸载、重载、升级和普通用户权限通过。
- `game_test`：手柄可完成启用、启动、读取真实 HTP 状态、停用与恢复；焦点顺序和长文本可读。
- 至少验证两项独立隔离：两个游戏配置不互写；不同 context/会话遥测不混为一个成功状态。单会话 MVP 可以拒绝第二个运行会话，并通过先后启动的会话验证状态隔离；只有声明支持多会话时才要求同时运行的隔离验收。
- 插件断开后运行链路正常，CLI 可独立恢复；没有 M6 证据的 mode 不显示为推荐。
- 记录截图/操作视频索引、宿主版本、失败场景与 gate；无设备部分保持 `not_run`。

## 9. 交接与 AI 提示词

交接包括宿主能力表、API 版本、AppID 来源证据、控制方法白名单、UI 状态图、竞态测试、手柄操作记录、恢复命令与升级限制。填写 [交接模板](../templates/handoff.md)，报告保存到 `docs/validation/M8/YYYY-MM-DD-<work-package>.md`，交接为同名 `-handoff.md`。

```text
实施 M8 的一个批次，先读取 M7 已有接口、公共合同和真实 Decky 宿主版本。
只做控制界面，禁止 Python/JS 传纹理或执行 QNN，禁止重复实现安装器。
不要假定 currentAppId 或 Steam 内部 API；先验证只读来源并提供明确手动选择。
每次请求捕获 appid/request_id/revision，返回时不使用变化后的当前游戏 ID。
复用 M7 plan/apply/restore，保留 Armada 启动参数，不擅自修改 Steam VDF。
真实 HTP/fresh/cached 与启用偏好分开显示。无设备用 mock 测试并标未实测。
按用户已有授权执行具体可恢复动作，输出证据、风险边界和 CLI 恢复路径。
```
