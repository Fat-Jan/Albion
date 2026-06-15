# STATUS

## Current

- M0-M6 已实现并线上运行。
- 当前版本：`1.0`，来源 `bot/version.py`。
- AI 辅助首发和只读查询增强已实现，AI 不参与审批、发组、撤组、改金额或发放标记。
- ZvZ 战报聚合/卡片模块已有单测，自动推送尚未接入。
- M7 出勤快照后置，等待真实用户反馈考勤口径。

## Harness

- 项目入口：`AGENTS.md`
- 长上下文事实：`notepad.md` 的 `## Priority Context`
- 操作文档：`README.md`、`使用说明书.md`
- 离线门禁：`scripts/check.sh`

## Next

1. 继续 KOOK 端活测和 AI 只读查询打磨。
2. 等真实用户反馈后再决定 M7 出勤口径。
3. 自动战报推送按 `docs/superpowers/specs/2026-06-14-battle-report-design.md` 另立任务接入。

## Verification

- 2026-06-15：`scripts/check.sh` 通过，83 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：`PYTHON_BIN=.venv/bin/python scripts/check.sh` 通过。

## Operational Notes

- 本地和线上不得同时使用同一个 `KOOK_TOKEN` 运行 bot。
- 本地 `.env` 若使用线上旧 token，服务器 `albion-kook.service` 必须保持停止。
- 升级服务器代码时不要替换服务器上的旧 `KOOK_TOKEN`。
- `.env`、数据库、日志和备份目录不得提交。
