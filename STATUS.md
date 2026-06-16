# STATUS

## Current

- M0-M6 已实现并线上运行。
- 本地双版本维护约定：`/Users/arm/Desktop/vscode/Albion-ASIA-kook` 使用 `deploy/asia` 分支维护亚服，`/Users/arm/Desktop/vscode/Albion-EU-kook` 使用 `deploy/eu` 分支维护欧服；`main` 只当共享上游主线，不直接作为某个服务器实例的长期工作分支。
- 分支同步规则：共享功能修复先做成独立提交，再 cherry-pick 到 `deploy/asia` 和 `deploy/eu`；不要整分支互 merge，因为接口默认值、`.env.example`、运行证据、公会名和部署记录必须各自保留。
- 已从欧服分支抽回通用区服配置化能力到亚服分支：AlbionBB 网页链接、官方击杀板 server、显示时区和自动战报窗口均可通过环境变量调整；亚服默认值继续保持 `gameinfo-sgp`、AODP `east`、albionbb `asia/east`、`live_sgp` 和北京时间窗口。
- 当前版本：`1.0`，来源 `bot/version.py`。
- AI 辅助首发、只读查询增强、`@机器人` 自然语言只读入口和高频卡片露出已实现；AI 现在会出现在补装审核卡和自动 ZvZ 战报卡，但不参与审批、发组、撤组、改金额或发放标记。
- ZvZ 战报聚合/卡片、AI 摘要、战报推送频道、最小本会参战人数阈值、最低 20 名本会参战者门槛、持久去重表和 `auto.py` 定时推送代码路径已接入；本机真实 KOOK 发送路径已确认战报只推到专属频道，线上 `albion-kook.service` 已切到日期参数修复版本，真实自动命中效果继续观察。
- M7 出勤快照后置，等待真实用户反馈考勤口径。

## Harness

- 项目入口：`AGENTS.md`
- 长上下文事实：`notepad.md` 的 `## Priority Context`
- 操作文档：`README.md`、`使用说明书.md`
- 离线门禁：`scripts/check.sh`
- VS Code 双目录入口：`/Users/arm/Desktop/vscode/Albion-ASIA-EU-kook.code-workspace`

## Next

1. 上线后观察 systemd 自动窗口：确认真实 AlbionBB 候选战役、北京时间窗口和线上去重日志。
2. 新功能同步流程：在当前要开发的实例分支完成并通过 `scripts/check.sh` 后，用 `git cherry-pick <功能提交>` 同步到另一实例分支；同步后复查 `bot/config.py`、`.env.example`、README/使用说明/STATUS/notepad 的区服默认值没有被带错。
3. 等真实用户反馈后再决定 M7 出勤口径。
4. 上线后观察 AI 摘要和补装审核提示的真实输出质量，必要时调整提示词和截断长度。

## Verification

- 2026-06-16：亚服本地同步欧服共享规则和自然语言入口收口。本轮只在亚服 `deploy/asia` 手工同步共享逻辑和文档，不整分支 merge，不改亚服区服默认值。战报自动推送现在运行时强制最低 20 名本会参战者才推送；击杀/死亡播报大额规则固定为击杀/死亡声望大于 100 万，或银币总损失大于 1000 万；低声望击杀也会按受害者装备+背包 `loss_total` 判断大额并展示损失估值；旧 `/设置 大额阈值` 仅提示固定规则，不再写入运行时配置；AI 配置概况也改为展示固定大额规则，并同步欧服 AI 战报字段清理、只读写操作拦截、`@机器人` 自然语言只读分发、昨晚/日期战报识别和显示名 mention 别名配置。`KOOK_BOT_MENTION_ALIASES` 默认留空，只在实例需要识别可见显示名时配置，避免写死 bot 名。验证：`.venv/bin/python -m unittest tests.test_battle_report tests.test_regear_flow tests.test_ai_module -v` 通过（102 个测试），`scripts/check.sh` 通过（140 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过。双边共享核心文件复查：`bot/tasks/auto.py`、`bot/cards/broadcast_cards.py`、`bot/ai/context.py`、`bot/ai/router.py`、`bot/commands/admin.py`、`bot/commands/ai.py`、`bot/commands/query.py`、`bot/store/db.py`、`tests/test_regear_flow.py` 与欧服一致；保留差异为区服默认值、AI system prompt 区服标识、区服链接/测试数据和文档实例事实。本轮未部署服务器，未启动真实 KOOK bot，未做 KOOK 真实活测。
- 2026-06-16：双版本共享能力同步收口。本轮只在亚服 `deploy/asia` 抽回通用配置化能力，保留亚服默认值；补充 `ALBIONBB_WEB_BASE`、`KILLBOARD_SERVER`、`DISPLAY_TZ*`、`BATTLE_REPORT_WINDOW_*` 到配置和文档入口，卡片/战报/自动任务改为读取配置；未整分支 merge，未启动本地 bot，未部署服务器。验证：`.venv/bin/python -m unittest tests.test_query_cards tests.test_battle_report -v` 通过（15 个测试），`scripts/check.sh` 通过（124 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过；配置探针确认默认仍为 `gameinfo-sgp`、AODP `east`、albionbb `asia/east`、`live_sgp`、`Asia/Shanghai`、北京时间 `14:30-05:00`。
- 2026-06-16：双分支差距复查。`git fetch --all --prune` 后确认亚服工作区在 `deploy/asia` 且跟踪 `origin/deploy/asia`，欧服工作区在 `deploy/eu` 且跟踪 `origin/deploy/eu`，两个本地工作区均干净。`git merge-base origin/deploy/eu origin/deploy/asia` 返回 `031571b`，说明亚服最新 `/战报 [日期]` 功能已经包含在欧服分支历史中；当前没有“亚服新功能未拉进欧服”的缺口。现存差异主要是欧服化提交 `7c87e63`，应保留在欧服分支，不整体同步回亚服；后续共享功能用 cherry-pick 双发。
- 2026-06-16：修复 KOOK `/战报 6-15` 仍返回 6 月 14 日摘要的问题。根因是 `/战报` 指令此前忽略参数，始终请求最近 8 场战役；连续查询时第二次 `/战报 6-15` 还会复用前一次 `/battles?limit=8` 的 120 秒缓存。现在 `/战报` 保持最近 8 场，`/战报 6-15`、`/战报 6月15`、`/战报 2026-06-15` 会按北京时间目标日 14:30 到次日 05:00 的 ZvZ 夜间窗口过滤，并用 `limit=51` 拉取候选。服务器真实 gameinfo 探针确认 Mika 拉取 51 条候选后，在 2026-06-15 窗口选出 49 场，前几场为 `480477649 2026-06-15T16:34:44Z`、`480476754 2026-06-15T16:32:08Z`、`480473108 2026-06-15T16:20:34Z`。已部署到阿里云新加坡 `/opt/albion-kook`，重启 `albion-kook.service` 后状态 `active/running`，PID `1208143`，启动时间 `2026-06-16 00:44:56 CST`；本轮也已把 README、使用说明书、实现计划、STATUS 和 notepad 同步到服务器目录。验证：本地 `.venv/bin/python -m unittest tests.test_ai_module -v` 通过，`scripts/check.sh` 通过（121 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过；服务器侧目标回归测试、全量 `unittest discover -s tests -q` 和 `compileall -q bot scripts tests` 通过。KOOK 命令二次触发需由真实用户账号发送；bot token 不能伪装用户触发自身命令。
- 2026-06-15：AI 高频露出版本已更新到阿里云新加坡 `/opt/albion-kook` 并切回服务器运行。上线前已将旧线上代码备份到 `/opt/albion-kook/releases/pre-ai-visibility-20260615_225328.tar.gz`；同步时保留服务器 `.env`、`.venv`、SQLite 数据库、日志和备份目录。服务器 `.env` 确认 `AI_ENABLED=true`、`AI_MODEL=LongCat-2.0-Preview`、`LONGCAT_API_KEY` 存在（未输出密钥原文）。线上代码包含 `summarize_battle_report`、战报卡「AI 摘要」和补装审核卡「AI 审核提示」。已重启 `albion-kook.service`，状态 `active/running`，PID `1205474`，启动时间 `2026-06-15 22:55:15 CST`，运行命令 `/opt/albion-kook/.venv/bin/python -m bot.main`；重启后日志显示 KOOK WebSocket 启动、定时任务注册、死亡播报轮询成功。服务器侧验证：`sudo -u albion .venv/bin/python -m bot.store.db` 成功，`sudo -u albion .venv/bin/python -m unittest discover -s tests -q` 通过（120 个测试），`sudo -u albion .venv/bin/python -m compileall -q bot scripts tests` 通过，`pragma integrity_check=ok`。
- 2026-06-15：AI 可见度增强离线实现完成；补装申请提交到审核频道时会先基于 `regear_explain_context()` 生成只读「AI 审核提示」，自动 ZvZ 战报推送会先基于 `battle_report_context()` 生成只读「AI 摘要」，异常时只记录 warning 并继续发送原卡片。新增回归覆盖补装审核卡 AI 提示、自动战报卡 AI 摘要、战报事实包和摘要 prompt 安全边界。验证：`.venv/bin/python -m unittest tests.test_battle_report tests.test_regear_flow tests.test_ai_module -v` 通过（83 个测试），`scripts/check.sh` 通过（120 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过。本轮尚未启动真实 KOOK bot 或重启线上 systemd；上线验证待后续执行。
- 2026-06-15：推送前线上收尾验证完成。先将本地当前代码同步到阿里云新加坡 `/opt/albion-kook`（保留服务器 `.env`、SQLite 数据库、日志和 `.venv`），线上执行 `sudo -u albion .venv/bin/python -m bot.store.db` 前已备份数据库到 `/opt/albion-kook/data/backups/bot-before-bind-migration-20260615_204315.db`；迁移后确认 `player_binding.custom_nickname`、`pending_approval.custom_nickname` 和 `battle_report_seen` 存在，`pragma integrity_check=ok`。已重启 `albion-kook.service`，状态 `active/running`，PID `1202429`，启动时间 `2026-06-15 20:43:30 CST`。按 `2026-06-15T12:21:04Z..12:51:04Z` 近 30 分钟 Albion 事件窗口补推 Mika 相关击杀/阵亡：匹配 107 条，跳过频道已有 52 条，实际补推 55 条；其中击杀频道 `5938739897296829` 补推 8 条，阵亡频道 `4201481428779754` 补推 47 条。KOOK `message/list` 游标反查确认补推事件均已在对应频道可见：击杀 8/8，阵亡 47/47。验证：本地 `scripts/check.sh` 通过（116 个单元测试 + `compileall bot scripts tests`），服务器侧 `sudo -u albion .venv/bin/python -m unittest discover -s tests -v` 与 `sudo -u albion .venv/bin/python -m compileall bot scripts tests` 退出码均为 0。
- 2026-06-15：新增 `/绑定 <角色名> [自定义昵称]` 逻辑；不新增绑定行，`player_binding` 与 `pending_approval` 增加 `custom_nickname` 列并带旧库幂等迁移，审批卡/结果卡显示目标 KOOK 昵称，审批通过或可信身份组快速通道会把 KOOK 昵称同步为 `角色名` 或 `角色名 - 自定义昵称`；AI 只读绑定事实包同步带 `custom_nickname`，并修复非白名单普通 AI 引导问题会因 `facts` 未定义报错的回归。真实 KOOK 活测：审批频道 `4503321752460202` 发绑定审批卡并原地更新结果卡成功；对测试用户 `1380312587` 使用真实 Albion 搜索 `BEISHENGS`（id `RhUAO9T3S5qVnsra3htx2g`，公会 `Mika`）跑完整审批，通过后 KOOK 昵称变为 `BEISHENGS - 北笙`，会员身份组 `47139243` 发放成功；随后已撤回会员身份组并删除本地测试绑定/待审批行。清理残留：昵称恢复为 `BEISHENGS` 被 KOOK 限流 `40000 操作过于频繁，请稍后再试` 阻断，需稍后重试。`tests.test_register_flow` 11 个测试通过，`tests.test_ai_module` 25 个测试通过，`scripts/check.sh` 通过，116 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：排查 ZheNiu `[Coup de grace]` → xbb11 `[Mika]` 死亡估值异常，确认事件 `480344381` 被 `T4_2H_SHAPESHIFTER_AVALON` 单个 `9,999,999` 当前挂单污染，旧逻辑估成 `8,534,118` 银；修复后当前挂单兜底价高于武器/副手本地低价参考 3 倍以上时按参考价封顶，并让 history 查询覆盖 1-5 品质以启用其他品质历史价兜底。真实事件复算：`480344381` 装备估值 `102,288` 银，`480345075` 装备估值 `449,066` 银；`scripts/check.sh` 通过，110 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：本地 SQLite 旧补装数据清理完成；清理前 `guild_binding=1`、`player_binding=3`、`regear_request=2`、`regear_reviewer_request=0`、`market_price_reference=6234`，已先备份到 `data/backups/bot-before-clear-regear-20260615_190645.db`，随后只清理 `regear_request` 和 `regear_reviewer_request` 并 `vacuum`；清理后 `regear_request=0`、`regear_reviewer_request=0`，其他计数不变，`pragma integrity_check` 返回 `ok`。
- 2026-06-15：绑定审批结果通知、补装审核/拒绝/发放通知闭环、补装审核身份申请结果通知、待审批卡申请号/状态展示和原卡片状态更新修复后，`scripts/check.sh` 通过，108 个单元测试通过，`compileall bot scripts tests` 通过；`git diff --check` 通过。本轮只做离线按钮回调/卡片渲染验证，未启动真实 KOOK bot 活测。
- 2026-06-15：`scripts/check.sh` 通过，90 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：本机真实 KOOK 测试战报 `codex-test-20260615173113` 通过 `auto._run_battle_report_tick()` 发往专属战报频道 `8139656704033247`；未 fetch/send 到统一/击杀频道 `5938739897296829` 或阵亡频道 `4201481428779754`；`battle_report_seen` 已写入去重记录。脚本退出时 khl.py 有未显式关闭 aiohttp session 的清理 warning，不影响发送断言结论。

## Operational Notes

- 本地和线上不得同时使用同一个 `KOOK_TOKEN` 运行 bot。
- 本地 `.env` 若使用线上旧 token，服务器 `albion-kook.service` 必须保持停止。
- 升级服务器代码时不要替换服务器上的旧 `KOOK_TOKEN`。
- `.env`、数据库、日志和备份目录不得提交。
