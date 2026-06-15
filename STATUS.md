# STATUS

## Current

- M0-M6 已实现并线上运行。
- 当前版本：`1.0`，来源 `bot/version.py`。
- AI 辅助首发和只读查询增强已实现，AI 不参与审批、发组、撤组、改金额或发放标记。
- ZvZ 战报聚合/卡片、战报推送频道、最小本会参战人数阈值、持久去重表和 `auto.py` 定时推送代码路径已接入；本机真实 KOOK 发送路径已确认战报只推到专属频道，线上 systemd 自动窗口尚未运行验证。
- M7 出勤快照后置，等待真实用户反馈考勤口径。

## Harness

- 项目入口：`AGENTS.md`
- 长上下文事实：`notepad.md` 的 `## Priority Context`
- 操作文档：`README.md`、`使用说明书.md`
- 离线门禁：`scripts/check.sh`

## Next

1. 上线后观察 systemd 自动窗口：确认真实 AlbionBB 候选战役、北京时间窗口和线上去重日志。
2. 等真实用户反馈后再决定 M7 出勤口径。
3. 继续 AI 只读查询打磨。

## Verification

- 2026-06-15：`scripts/check.sh` 通过，90 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：本机真实 KOOK 测试战报 `codex-test-20260615173113` 通过 `auto._run_battle_report_tick()` 发往专属战报频道 `8139656704033247`；未 fetch/send 到统一/击杀频道 `5938739897296829` 或阵亡频道 `4201481428779754`；`battle_report_seen` 已写入去重记录。脚本退出时 khl.py 有未显式关闭 aiohttp session 的清理 warning，不影响发送断言结论。

## Operational Notes

- 本地和线上不得同时使用同一个 `KOOK_TOKEN` 运行 bot。
- 本地 `.env` 若使用线上旧 token，服务器 `albion-kook.service` 必须保持停止。
- 升级服务器代码时不要替换服务器上的旧 `KOOK_TOKEN`。
- `.env`、数据库、日志和备份目录不得提交。
