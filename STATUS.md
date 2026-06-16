# STATUS

## Current

- M0-M6 已实现；欧服本地代码、配置默认值和文档默认标识已完成适配，欧服线上部署状态未确认。
- 本地双版本维护约定：`/Users/arm/Desktop/vscode/Albion-EU-kook` 使用 `deploy/eu` 分支维护欧服，`/Users/arm/Desktop/vscode/Albion-ASIA-kook` 使用 `deploy/asia` 分支维护亚服；`main` 只当共享上游主线，不直接作为某个服务器实例的长期工作分支。
- 分支同步规则：共享功能修复先做成独立提交，再 cherry-pick 到 `deploy/eu` 和 `deploy/asia`；不要把 `deploy/eu` 整体 merge 到 `deploy/asia`，也不要反向整体 merge，因为接口默认值、`.env.example`、运行证据、公会名和部署记录必须各自保留。
- 已与亚服分支同步通用区服配置化能力：AlbionBB 网页链接、官方击杀板 server、显示时区和自动战报窗口均可通过环境变量调整；欧服默认值继续保持 `gameinfo-ams`、AODP `europe`、albionbb `eu/europe`、`live_ams` 和北京时间窗口。
- 当前版本：`1.0`，来源 `bot/version.py`。
- AI 辅助首发、只读查询增强和高频卡片露出已实现；AI 现在会出现在补装审核卡和自动 ZvZ 战报卡，但不参与审批、发组、撤组、改金额或发放标记。
- ZvZ 战报聚合/卡片、AI 摘要、战报推送频道、最小本会参战人数阈值、持久去重表和 `auto.py` 定时推送代码路径已接入；欧服线上真实自动窗口待单独部署/确认后验证。
- M7 出勤快照后置，等待真实用户反馈考勤口径。

## Harness

- 项目入口：`AGENTS.md`
- 长上下文事实：`notepad.md` 的 `## Priority Context`
- 操作文档：`README.md`、`使用说明书.md`
- 离线门禁：`scripts/check.sh`
- VS Code 双目录入口：`/Users/arm/Desktop/vscode/Albion-ASIA-EU-kook.code-workspace`

## Next

1. 如需部署欧服实例，先明确目标服务器/目录/token 边界；不要把 `/opt/albion-kook` 的亚服旧服务默认当作欧服线上。
2. 新功能同步流程：在当前要开发的实例分支完成并通过 `scripts/check.sh` 后，用 `git cherry-pick <功能提交>` 同步到另一实例分支；同步后复查 `bot/config.py`、`.env.example`、README/使用说明/STATUS/notepad 的区服默认值没有被带错。
3. 欧服部署后观察 systemd 自动窗口：确认真实 AlbionBB 候选战役、北京时间窗口和线上去重日志。
4. 等真实用户反馈后再决定 M7 出勤口径。
5. 欧服实例部署并启用后观察 AI 摘要和补装审核提示的真实输出质量，必要时调整提示词和截断长度。

## Verification

- 2026-06-16：双版本共享能力同步到欧服。本轮从亚服 `deploy/asia` cherry-pick 通用配置化提交并保留欧服默认值；`ALBIONBB_WEB_BASE`、`KILLBOARD_SERVER`、`DISPLAY_TZ*`、`BATTLE_REPORT_WINDOW_*` 继续可配置，卡片/战报/自动任务读取配置；未启动本地 bot，未部署服务器。验证：`.venv/bin/python -m unittest tests.test_query_cards tests.test_battle_report -v` 通过（15 个测试），`scripts/check.sh` 通过（124 个单元测试 + `compileall bot scripts tests`），`git diff --check HEAD` 通过；配置探针确认默认仍为 `gameinfo-ams`、AODP `europe`、albionbb `eu/europe`、`live_ams`、`Asia/Shanghai`、北京时间 `14:30-05:00`。
- 2026-06-16：双分支差距复查。`git fetch --all --prune` 后确认 `/Users/arm/Desktop/vscode/Albion-EU-kook` 在 `deploy/eu` 且跟踪 `origin/deploy/eu`，`/Users/arm/Desktop/vscode/Albion-ASIA-kook` 在 `deploy/asia` 且跟踪 `origin/deploy/asia`，两个本地工作区均干净。`git merge-base origin/deploy/eu origin/deploy/asia` 返回 `031571b`，也就是亚服最新 `fix(战报): 支持按日期查询 AI 摘要` 已经包含在欧服分支历史中；当前没有“亚服新功能未拉进欧服”的缺口。现存差异主要是欧服化提交 `7c87e63`：欧服接口默认值、AI system prompt 区服标识、AlbionBB 网页链接配置化、北京时间显示测试、欧服接口文档和双工作区说明。处理结论：功能用 cherry-pick 双发；区服默认值和实例证据不做整分支互 merge。
- 2026-06-16：真正欧服化收口复查。已确认本地 runtime 读取欧服默认：`GAMEINFO_BASE=https://gameinfo-ams.albiononline.com/api/gameinfo`、`AODP_BASE=https://europe.albion-online-data.com`、`ALBIONBB_BASE=https://api.albionbb.com/eu`、`ALBIONBB_WEB_BASE=https://europe.albionbb.com`、`KILLBOARD_SERVER=live_ams`，运行环境仍为本地 `.venv` + `DB_PATH=data/bot.db`。公网只读探针：gameinfo `/search?q=Top%20Squad` 返回 200（命中公会 `Top Squad`，id `7tmt12sOTkGgcqZL3jSy7Q`；详情接口返回 Founder `Soxxx`、MemberCount 154），AODP `/api/v2/stats/gold.json?count=1` 返回 200（rows=1），AlbionBB `/eu/battles?minPlayers=20&page=1` 返回 200（rows=20）。已用欧服 AODP 刷新本地武器/副手市场挂单低价参考：`.venv/bin/python -m scripts.refresh_price_reference` 输出 `items=3875 api_rows=116250 records=10595`；SQLite 复查 `market_price_reference=10595`、source=`aodp_prices_sell_min`、mainhand=9351、offhand=1244、`pragma integrity_check=ok`。文档同步：`欧服接口调研.md` 改为当前欧服状态，harness 计划中的“当前线上服务”改为亚服旧服务残留。本轮未启动真实 KOOK bot、未重启、未部署、未修改任何服务器。
- 2026-06-16：澄清部署记录。阿里云新加坡 `/opt/albion-kook` 更可能是亚服旧服务/旧文档残留，不应作为欧服线上验收依据：该目录只读检查时不是 git 工作树，`.env` 仍覆盖 `GAMEINFO_BASE=https://gameinfo-sgp.albiononline.com/api/gameinfo`、`AODP_BASE=https://east.albion-online-data.com`、`ALBIONBB_BASE=https://api.albionbb.com/asia`；服务 `albion-kook.service` active/running，PID `1208143`，但未证明属于欧服实例。本轮未修改服务器、未重启 bot。欧服当前可确认范围是本地仓库适配和本地/公网接口验证。
- 2026-06-16：迁移说明。以下 2026-06-15 到 2026-06-16 的 `/opt/albion-kook`、阿里云新加坡和 `albion-kook.service` 记录保留为迁移来源/亚服旧项目历史，不作为欧服已部署、欧服已运行或欧服 KOOK 活测证据。欧服验收以当前仓库默认配置、欧服公网接口探针、离线门禁和后续明确的欧服实例验证为准。
- 2026-06-16：复查欧服改造完成面。结论：本地代码默认值、`.env.example`、本机 `.env`、README/使用说明/接口文档/实现计划中的默认标识均已欧服化；亚服字符串只允许出现在手动回切示例、其他区说明或已标注迁移历史中，不作为默认配置。仓库根目录已调整为 `/Users/arm/Desktop/vscode/Albion-EU-kook`，不再保留旧内层目录名。新鲜验证：本地运行时配置读到 `gameinfo-ams`、AODP `europe`、albionbb `eu`、`KILLBOARD_SERVER=live_ams`；公开接口探针 gameinfo/AODP/AlbionBB 均返回 200。
- 2026-06-16：欧服接口和代码标识复查完成。代码默认值、`.env.example`、本机 `.env` 非密钥区服键均为欧服三件套：`GAMEINFO_BASE=https://gameinfo-ams.albiononline.com/api/gameinfo`、`AODP_BASE=https://europe.albion-online-data.com`、`ALBIONBB_BASE=https://api.albionbb.com/eu`、`ALBIONBB_WEB_BASE=https://europe.albionbb.com`、`KILLBOARD_SERVER=live_ams`；AI system prompt、卡片提示、README、使用说明书、实现计划、接口文档和 harness 设计残留已同步为欧服默认。公开接口探针确认 gameinfo `/search?q=Top%20Squad`、AODP `/api/v2/stats/gold.json?count=1`、AlbionBB `/eu/battles?minPlayers=20&page=1` 均返回 200；本地 SQLite 当前绑定为 KOOK guild `5204615975879655` -> Albion guild `Top Squad` (`7tmt12sOTkGgcqZL3jSy7Q`)。旧亚服字符串复扫后不再作为接口、配置默认值、文档默认标识或本地运行环境出现。验证：`scripts/check.sh` 通过（123 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过。本轮未启动真实 KOOK bot、未重启或修改服务器服务。
- 2026-06-16：【亚服旧项目记录/迁移残留】修复 KOOK `/战报 6-15` 仍返回 6 月 14 日摘要的问题。根因是 `/战报` 指令此前忽略参数，始终请求最近 8 场战役；连续查询时第二次 `/战报 6-15` 还会复用前一次 `/battles?limit=8` 的 120 秒缓存。现在 `/战报` 保持最近 8 场，`/战报 6-15`、`/战报 6月15`、`/战报 2026-06-15` 会按北京时间目标日 14:30 到次日 05:00 的 ZvZ 夜间窗口过滤，并用 `limit=51` 拉取候选。历史服务器 gameinfo 探针曾确认 Mika 拉取 51 条候选后，在 2026-06-15 窗口选出 49 场，前几场为 `480477649 2026-06-15T16:34:44Z`、`480476754 2026-06-15T16:32:08Z`、`480473108 2026-06-15T16:20:34Z`。旧记录曾写入阿里云新加坡 `/opt/albion-kook` 并重启 `albion-kook.service`，但 2026-06-16 欧服复查发现该目录仍是亚服配置，不能作为欧服部署证据。验证：本地 `.venv/bin/python -m unittest tests.test_ai_module -v` 通过，`scripts/check.sh` 通过（121 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过；旧服务器侧目标回归测试、全量 `unittest discover -s tests -q` 和 `compileall -q bot scripts tests` 通过。KOOK 命令二次触发需由真实用户账号发送；bot token 不能伪装用户触发自身命令。
- 2026-06-15：【亚服旧项目记录/迁移残留】AI 高频露出版本曾更新到阿里云新加坡 `/opt/albion-kook` 并切回服务器运行。旧记录中的备份、`.env`、`.venv`、SQLite、日志、`AI_ENABLED=true`、`AI_MODEL=LongCat-2.0-Preview`、`albion-kook.service active/running` 和服务器侧测试，只能说明迁移前亚服服务当时状态；不能作为欧服实例已上线证据。
- 2026-06-15：AI 可见度增强离线实现完成；补装申请提交到审核频道时会先基于 `regear_explain_context()` 生成只读「AI 审核提示」，自动 ZvZ 战报推送会先基于 `battle_report_context()` 生成只读「AI 摘要」，异常时只记录 warning 并继续发送原卡片。新增回归覆盖补装审核卡 AI 提示、自动战报卡 AI 摘要、战报事实包和摘要 prompt 安全边界。验证：`.venv/bin/python -m unittest tests.test_battle_report tests.test_regear_flow tests.test_ai_module -v` 通过（83 个测试），`scripts/check.sh` 通过（120 个单元测试 + `compileall bot scripts tests`），`git diff --check` 通过。本轮尚未启动真实 KOOK bot 或重启任何 systemd；真实实例验证待后续执行。
- 2026-06-15：【亚服旧项目记录/迁移残留】推送前线上收尾验证曾将当时本地代码同步到阿里云新加坡 `/opt/albion-kook`，保留服务器 `.env`、SQLite、日志和 `.venv`，并重启 `albion-kook.service` 后做 KOOK 补推反查。该记录属于亚服迁移来源，不代表当前欧服仓库已部署或欧服 KOOK 已活测。
- 2026-06-15：新增 `/绑定 <角色名> [自定义昵称]` 逻辑；不新增绑定行，`player_binding` 与 `pending_approval` 增加 `custom_nickname` 列并带旧库幂等迁移，审批卡/结果卡显示目标 KOOK 昵称，审批通过或可信身份组快速通道会把 KOOK 昵称同步为 `角色名` 或 `角色名 - 自定义昵称`；AI 只读绑定事实包同步带 `custom_nickname`，并修复非白名单普通 AI 引导问题会因 `facts` 未定义报错的回归。真实 KOOK 活测：审批频道 `4503321752460202` 发绑定审批卡并原地更新结果卡成功；对测试用户 `1380312587` 使用真实 Albion 搜索 `BEISHENGS`（id `RhUAO9T3S5qVnsra3htx2g`，公会 `Mika`）跑完整审批，通过后 KOOK 昵称变为 `BEISHENGS - 北笙`，会员身份组 `47139243` 发放成功；随后已撤回会员身份组并删除本地测试绑定/待审批行。清理残留：昵称恢复为 `BEISHENGS` 被 KOOK 限流 `40000 操作过于频繁，请稍后再试` 阻断，需稍后重试。`tests.test_register_flow` 11 个测试通过，`tests.test_ai_module` 25 个测试通过，`scripts/check.sh` 通过，116 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：排查 ZheNiu `[Coup de grace]` → xbb11 `[Mika]` 死亡估值异常，确认事件 `480344381` 被 `T4_2H_SHAPESHIFTER_AVALON` 单个 `9,999,999` 当前挂单污染，旧逻辑估成 `8,534,118` 银；修复后当前挂单兜底价高于武器/副手本地低价参考 3 倍以上时按参考价封顶，并让 history 查询覆盖 1-5 品质以启用其他品质历史价兜底。真实事件复算：`480344381` 装备估值 `102,288` 银，`480345075` 装备估值 `449,066` 银；`scripts/check.sh` 通过，110 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：本地 SQLite 旧补装数据清理完成；清理前 `guild_binding=1`、`player_binding=3`、`regear_request=2`、`regear_reviewer_request=0`、`market_price_reference=6234`，已先备份到 `data/backups/bot-before-clear-regear-20260615_190645.db`，随后只清理 `regear_request` 和 `regear_reviewer_request` 并 `vacuum`；清理后 `regear_request=0`、`regear_reviewer_request=0`，其他计数不变，`pragma integrity_check` 返回 `ok`。
- 2026-06-15：绑定审批结果通知、补装审核/拒绝/发放通知闭环、补装审核身份申请结果通知、待审批卡申请号/状态展示和原卡片状态更新修复后，`scripts/check.sh` 通过，108 个单元测试通过，`compileall bot scripts tests` 通过；`git diff --check` 通过。本轮只做离线按钮回调/卡片渲染验证，未启动真实 KOOK bot 活测。
- 2026-06-15：`scripts/check.sh` 通过，90 个单元测试通过，`compileall bot scripts tests` 通过。
- 2026-06-15：本机真实 KOOK 测试战报 `codex-test-20260615173113` 通过 `auto._run_battle_report_tick()` 发往专属战报频道 `8139656704033247`；未 fetch/send 到统一/击杀频道 `5938739897296829` 或阵亡频道 `4201481428779754`；`battle_report_seen` 已写入去重记录。脚本退出时 khl.py 有未显式关闭 aiohttp session 的清理 warning，不影响发送断言结论。

## Operational Notes

- 同一个 `KOOK_TOKEN` 不得被两个 bot 进程同时使用。
- 本地 `.env` 若使用某个已确认欧服实例的 token，必须先停止对应实例再本地启动。
- 升级已确认的服务器实例时不要替换服务器上的旧 `KOOK_TOKEN`。
- `.env`、数据库、日志和备份目录不得提交。
