# M0 FIRST_BATCH host integration handoff

## 当前现场

- 工作包：FIRST_BATCH I；owner：主 integrator。
- 批次基线：`fbe0b1d36155b58ec936c0d4e5f7d8b5c015c23d`；最终已审修复 Head：`5c5775be613a37c81c1d3f6a2552f6951d3bb56e`。
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
| I 修复 | fixture/公开 evidence containment、进程树所有权、结构化脱敏和协议字段保护 | `2026-09-20-review-fixes.md` |
| Astra | 初审 change；Sol 定点修复后定点复审 pass | `2026-09-20-first-batch-rereview.md` |

## 尚未完成或验证

- Linux 普通文件 symlink、POSIX 进程组、SIGALRM、真实 procfs/sysfs/权限和进程行为 `not_run`。
- Odin 3 `device_test: not_run`，game_test `not_run`；没有安装/提权/刷机/解锁/配置修改。
- 残余审阅风险：路径检查/open 间 TOCTOU；公开写入 I/O 失败可能留下部分新产物。

## 下一步

1. 在 Linux 开发主机补跑两个普通文件 symlink、POSIX 进程组、SIGALRM 和真实只读文件行为；仍不得当作 Odin 3 验证。
2. 设备所有者提供明确访问方式后执行 M0-C，只读采集并人工对照关键字段。
3. 保存新的 `device_profile_id`、工具 commit、权限不足项和真实原始证据；公开提交前运行 `redact`。
4. 只有真实设备门槛满足后才完成 M0；当前状态保持 `in_progress` / host pass / device not_run。
