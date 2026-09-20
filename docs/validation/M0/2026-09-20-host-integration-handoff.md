# M0 FIRST_BATCH host integration handoff

## 当前现场

- 工作包：FIRST_BATCH I；owner：主 integrator。
- 基线：`91ae78e2042a4c8971b39a8abd381a0705ab7085`；集成结果尚待提交和 Astra 审阅。
- 主协调器实际精确模型/推理强度不可见；项目配置声明 GPT-5.6 Sol / medium。
- Worker A/B 角色由宿主的 `fsr4_worker` 配置创建（GPT-5.6 Sol / medium）；各自未操作 Git。
- Windows/Python 主机可用；无 Odin 3、SDK、专有资产或游戏环境。

## 已完成的变化

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| S0 | schema、CLI、fixture/runner、依赖已冻结 | `2026-09-20-schema-contract.md` |
| A | Linux 只读 collector 与说明 | `2026-09-20-collector.md` |
| B | validate/redact、golden fixture、测试 | `2026-09-20-offline-tools.md` |
| I | A→B 私有校验→公开脱敏→公开校验组合通过 | `2026-09-20-host-integration.md` |
| I 修复 | evidence resolved path containment；新增 symlink 逃逸测试 | 同上（Windows 触发测试 skip） |

## 尚未完成或验证

- Astra 尚未审阅冻结 diff；其裁决不等于设备通过。
- Linux evidence symlink 触发测试、真实 procfs/sysfs/权限和进程行为 `not_run`。
- Odin 3 `device_test: not_run`，game_test `not_run`；没有安装/提权/刷机/解锁/配置修改。

## 下一步

1. 提交当前主机批次以冻结 Base/Head，生成 review packet。
2. 由 `fsr4_reviewer` 直接审 diff、源码和本批报告。
3. Sol 只修具体发现并跑受影响检查；Astra 只复审修复范围。
4. 审阅通过后由 integrator 更新 `docs/STATUS.md` 为 M0 `in_progress`、host_test `pass`，保持 device/game `not_run`。

