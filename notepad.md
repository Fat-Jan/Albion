# Notepad — 阿尔比恩公会 KOOK 机器人

> 项目本地续接记录。会话启动读 `## Priority Context`。

## Priority Context

- 项目是面向单个亚服公会的 KOOK 机器人，两条主线：管理员绑公会 + 玩家自助绑角色（名字匹配+审批），绑定后查询免输名字。
- `README.md` / `使用说明书.md` 作为通用亚服版本说明维护；Mika 公会、阿里云实例、真实频道 ID 和活测证据继续留在 `STATUS.md` / 本文件，不回灌到通用 README。
- 当前进度：**M0-M6 已实现并线上运行**，数据/逻辑对真实 API 验过；补装、播报、查询已在真实 bot 进程中跑。当前项目版本 `1.0`（`bot/version.py`，`/ping` 返回 `pong v1.0`）。AI 辅助已扩展为高频只读露出：`/助手`、`/战报 [日期]`、`/补装解释`、`@机器人` 自然语言只读入口、补装审核卡「AI 审核提示」、自动 ZvZ 战报卡「AI 摘要」；`/战报 6-15`、自然语言“昨晚战报/昨晚的战役”等日期参数按北京时间目标日 14:30 到次日 05:00 过滤。AI 仍不得审批、发组、撤组、改金额或标记发放。M7 出勤后置，等真实用户反馈明确考勤口径后再做。
- 项目已采用轻量 harness：后续接手先读 `AGENTS.md` 和 `STATUS.md`；离线门禁统一跑 `scripts/check.sh`。离线通过不等于 KOOK 真实交互已活测，涉及线上/真实 bot 的结论必须补充活测证据。
- 测试用 KOOK 服务器可换（当前 id `4676167053713576`，bot 身份 Jianguomao#7691 只是当前测试身份）；绑定一律按运行时 guild_id 走，代码不写死服务器，机器人显示名别名也只通过 `KOOK_BOT_MENTION_ALIASES` 显式配置。当前测试服必须使用 `asia-` 前缀频道：`asia-✅绑定审批` `6280501542155342`、`asia-📢成员变动` `1203064556541945`、`asia-⚔️击杀播报` `4326560318750543`、`asia-💀阵亡播报` `5193310241387334`、`asia-🗺️战报推送` `3891092612097998`、`asia-📥补装申请` `8092855830265715`、`asia-🔍补装审核` `2772001930672157`、`asia-💰补装发放` `9380523626852434`、`asia-📣补装通知` `9980001624642186`；旧无前缀补装频道不再作为当前配置使用。`📯丨战报推送` `8139656704033247`、`击杀播报` `5938739897296829`、`死亡播报` `4201481428779754` 此前确实承载过亚服推送，但已被 `asia-` 前缀专用频道替代，并经用户点名授权删除；本地库残留 `broadcast_channel_id=5938739897296829` 已备份后清空。
- 测试参考角色：armskey/muaowo（都不在 Mika）；需要 Mika 成员就从 `/guilds/{id}/members` 挑活跃的。
- 实际运行环境是 **Python 3.13.12**（计划写 3.11+），khl.py 0.3.17 / httpx 0.28.1 / python-dotenv，3.13 兼容无碍；venv 在 `.venv/`。
- 技术栈定死：Python + khl.py（WebSocket）+ httpx + SQLite；数据源默认走亚服三件套（gameinfo-sgp / east AODP / albionbb-asia），AlbionBB 网页链接、官方击杀板 server、显示时区和自动战报窗口已配置化，亚服默认仍是 east.albionbb.com / live_sgp / 北京时间窗口，别混区。
- 所有设计决议已收口进 `KOOK机器人实现计划.md` 第十一节，无遗留待定项。
- 项目 GitHub 仓库地址：`https://github.com/Fat-Jan/Albion.git`，本地 Git remote `origin` 已指向该地址。
- 仓库与分支真相：远端仓库为 `https://github.com/Fat-Jan/Albion.git`；亚服目录 `/Users/arm/Desktop/vscode/Albion-ASIA-kook` 固定使用 `deploy/asia` 分支；欧服目录 `/Users/arm/Desktop/vscode/Albion-EU-kook` 固定使用 `deploy/eu` 分支；`main` 只当共享上游主线，不直接作为某个服务器实例长期开发分支。双目录 VS Code 入口在 `/Users/arm/Desktop/vscode/Albion-ASIA-EU-kook.code-workspace`。
- 功能同步规则：共享功能修复用独立提交双向 cherry-pick；不要整分支互 merge。整分支 merge 会把区服接口默认值、`.env.example`、公会名、运行证据和部署记录混进另一实例。
- 当前线上服务：阿里云新加坡 `aliyun_singapore` 上的 `albion-kook.service`，目录 `/opt/albion-kook`，日志 `/var/log/albion-kook/bot.log`；线上继续使用旧 KOOK bot/token。2026-06-16 00:44 已切回服务器运行 `/战报 [日期]` 修复版本，PID `1208143`，启动命令 `/opt/albion-kook/.venv/bin/python -m bot.main`；服务器 `.env` 已开启 AI 且保留旧 token/key。后续升级服务器时**不要替换服务器上的旧 `KOOK_TOKEN`**。若后续改回独立开发 bot token，本地可不停服务器直接调试。
- 当前数据库概况（2026-06-18 复查）：`guild_binding=1`、`player_binding=2`、`pending_approval=5`、`regear_request=0`、`regear_reviewer_request=0`、`market_price_reference=6234`，`pragma integrity_check=ok`。测试服 `4676167053713576` 当前 `broadcast_channel_id=None`、`battle_report_channel_id=3891092612097998`，旧三播报频道字段命中 `old_three_hits=none`。2026-06-18 交叉比对亚服/欧服 `4676167053713576` 的运营+补装 9 个频道字段，`shared_count=0`；本地亚服 bot PID `77525`，token 诊断 `bot_id=49025 token_fp=45a5a99e7b1b token_source=env_file`。

## 已收口的关键决议（2026-06-14）

- 死亡播报 + 退会复查放**一期**一起做，共用 asyncio 定时轮询骨架；退会复查通知优先走 `member_change_channel_id`（`/设置 成员变动频道 #频道`），未配置时兜底播报频道再兜底审批频道。
- 估值默认口径：红城近 7 天 `avg_price`（走 AODP `/history` time-scale=24），稀疏回退多城近 7 天 avg_price 中位，过滤 0 与离群（>中位 3 倍剔除）。同品质无价时，同物品其他品质 history 或 `/prices` sell_min 按 ×0.85 兜底，避免派系/Avalon/高 tier 低频武器主副手估 0。补装金额只算穿戴装备，背包物品仅在详情/播报总损失中展示，不计入补装；补装审核卡必须明示该口径。`/prices` 现价也给 `/物价`。
- 所有权验证：方案二（名字匹配+审批）+ KOOK 角色预检做**信心分级**（持可信身份组+API 命中可快速通过），非硬门槛，避免新人死锁。
- 功能盘对比同类 bot 后一期补：`/金价`、`/榜单`、死亡播报分击杀/阵亡+大额高亮、`/补装`（复用估值+审批）；`/出勤`只做最近 N 场快照，趋势版+采集器归二期。
- 明确不做：经济/虚拟银行/税、CTA 排期、运输套利、武器对战矩阵。
- 物品中文名接 ao-bin-dumps `LocalizedNames["ZH-CN"]`，预处理成本地 dict 随包，不运行时拉 GitHub。
- 大额播报规则固定：击杀/死亡声望大于 100 万，或银币总损失大于 1000 万时高亮；`/设置 大额阈值` 仅保留旧命令兼容提示，不再改变运行时规则。
- 文档入口：`README.md` 已更新为当前状态；`使用说明书.md` 已新增，覆盖管理员初始化、成员绑定、补装流程、自动任务、估值口径和运维排错。
- AI 辅助：已按“受控 AI 服务 + 窄白名单只读路由”上线，使用 LongCat/OpenAI 兼容接口（当前模型 `LongCat-2.0-Preview`）。AI 当前会出现在 `/战报`、`/助手`、`/补装解释`、补装审核卡「AI 审核提示」和自动 ZvZ 战报卡「AI 摘要」；不进入绑定审批、补装审批、金额改写、发组/撤组或发放标记链路。普通成员通过 `/助手` 可查本人绑定状态、最近击杀/阵亡、本人补装状态，管理员/补装审核员可查全服补装队列，管理员可查频道配置概况。AI 事实包带 `schema_version/tool`，输出层拦截危险动作声明并脱敏疑似 Token/API Key；AI 回复凡提到时间必须标注口径：服务器/API 时间 UTC、数据库/服务器时间 UTC，或北京时间 UTC+8。
- 版本号控制：当前版本 `1.0`，代码单一来源是 `bot/version.py`；`bot.main.ping_text()` 使用同一来源，测试见 `tests/test_version.py`。
- 战报推送：`bot/albion/battle_report.py`、`bot/cards/battle_report_cards.py`、`bot/tasks/auto.py` 已接入聚合、卡片、AI 摘要、北京时间窗口、专属频道推送、本会最小人数阈值和 SQLite 持久去重；`/设置 战报推送频道`、`/设置 战报频道`、`/设置 战报本会最小人数` 已接入，运行时最低 20 名本会参战者才推送。2026-06-15 本机真实 KOOK 发送路径曾确认测试战报只推到当时的专属战报频道 `8139656704033247`，没有走统一/击杀频道 `5938739897296829` 或阵亡频道 `4201481428779754`，并写入 `battle_report_seen`；2026-06-18 已迁移为 `asia-🗺️战报推送` `3891092612097998`。22:55 已部署到线上 systemd，真实自动命中和 AI 摘要质量继续看日志和频道输出，不要提前写成已稳定命中。

## 坑点 / 注意

- 亚服 AODP 市场稀疏 + 有离群噪音（实测某城 T4_BAG 挂单 333333），估值必须兜底，不取单点。
- 官方 API 偶发数天故障（社区常态），所有调用要容错 + 退避。
- KOOK 每日发消息上限 1 万，死亡播报要控频 + 去重。
- murderledger / albiondb 有 Cloudflare 拦截，程序化用不了，只能官方源自己聚合。
- 玩家/公会查询要先 `/search` 拿 base64 ID 再查详情。
- **khl.py 权限坑**：消息作者 GuildUser 的 `guild_id` 为空，`user.fetch_roles()` 会以空 id 请求 `guild-role/list` 报 400。正确做法：`guild.fetch_roles()` 拉全量 + 作者 `user.roles` id 列表求交集（见 `bot/perms.py`）。
- 管理权限判定按位：管理员(0)/管理服务器(1)/管理频道(5)/管理角色(10) 任一即放行（频道管理员及以上）。
- **官方 `/events?guildId=` 只回本会"击杀"，不含"阵亡"**（实证：真实阵亡事件翻 4 页都不在 guild feed）。死亡播报改走**全局 `/events` 多页 + 双向筛**（killer/victim 任一是本会）。普通时段每 4 分钟拉 4 页，20:00-00:30 每 90 秒拉 4 页；亚服全局约 36 事件/分钟，常规覆盖足够，ZvZ 突发超覆盖会丢少量（已记日志、控频 15 条/轮）。
- khl 卡片：`channel.send(CardMessage)` 自动按 type=CARD 发；按钮值用 JSON {act, ...}，多个 on_event(MESSAGE_BTN_CLICK) handler 各自按 act 过滤。链接按钮用 `Element.Button(text, url, Types.Click.LINK)`。
- **物品翻译坑**：派系坐骑等特殊物品 UniqueName 自带 `@N`（如 `T5_MOUNT_COUGAR_KEEPER@1`=迅爪），基名查不到 → `items.localized` 已加整串直查兜底。`items.tier_enchant` 从 id 解析 `T层级.附魔` 标注。
- 时间口径：官方 API 全 UTC；卡片用 `query_cards.beijing()` 加「北京 MM-DD HH:MM」注释（UTC+8）。AI 事实包不提供裸时间，统一给服务器/API 时间 UTC + 北京时间 UTC+8；数据库时间标为数据库/服务器时间 UTC。
- 死亡详情：`/补装` 列表每条带 [详情]（出装备明细+估值+官方击杀板链接 `albiononline.com/killboard/kill/{EventId}?server=live_sgp`）和 [选这个补装]。
- 补装流程：已有 SQLite `regear_request` 管理申请。`pending`=待审批，审批通过前会重新按当前估值刷新金额并落 `approved`=待发放；线下发银/物资后点 [标记已发放] 落 `paid`（独立 `paid_by/paid_at`，不覆盖 `reviewed_by/reviewed_at`）。补装审核已和 KOOK 管理员权限解耦：管理员用 `/设置 补装审核身份组 @身份组` 配置后，成员可 `/补装审核` 申请该身份，管理员审批通过会自动发组；之后持该身份组的人可 `/补装 待处理`、`/补装 待发放`、`/补装 列表` 并审批/拒绝/标记发放。补装中心已改为四频道：`regear_apply_channel_id`（成员 `/补装`、`/补装状态`）、`regear_review_channel_id`（审核卡）、`regear_payout_channel_id`（待发放卡）、`regear_notify_channel_id`（完成通知，只 @ 成员不公开金额/事件）。推荐 `/设置 补装初始化频道` 新建或复用当前区服前缀补装中心（亚服为 `asia-🛡️补装中心`）；旧 `regear_channel_id`/`/设置 补装频道` 仅作兼容兜底，不复用旧频道。
- **武器/副手低价参考库**：SQLite `market_price_reference` 已落地，范围是 T4-T8 的 `MAIN_`/战斗类 `2H_`/`OFF_`，包含未附魔和 `@1~@4`，按品质 1-5 存各城 `sell_price_min` 的低价参考（剔除高离群）。补装/估值仍优先 history 与实时 `/prices`，实时拿不到时才用库内参考价兜底。手动刷新：`.venv/bin/python -m scripts.refresh_price_reference`；机器人运行后每 3 天自动刷新一次。2026-06-14 首次真实刷新：3875 个物品 id，116250 条 API 行，写入 6234 条 `(item_id, quality)` 参考价。
- **死亡事件地点官方不给（已定论）**：复验全局 51 条 + 历史 357 条，`KillArea` 全 `OPEN_WORLD`，`Location`/`Category`/`GvGMatch` 全 `null`，16 个顶层字段无其它地理字段。SBI 故意不对公开 API 暴露死亡地图（论坛多年请求未果）；第三方站（同源数据 + CF 拦截）与客户端 Photon 抓包（服务器 bot 不在现场）均不可行 → 地点显示无意义。播报卡、补装卡和 `/估值` 已去掉地点展示，只保留时间、IP 和规模。
- **玩家 kills/deaths 端点锁最近 10 条**，`limit`/`offset` 无效，抓不到更多历史。
- **遭遇规模分层预估**：`numberOfParticipants` 是"补刀人数"（常=4，会把 ZvZ 误标小团，已弃用）。改用 `GroupMembers`(=主角所在小队，恒含主角本人) 做队伍口径 `scale_label`（单人1/小团2-7/团战8-20/ZvZ20+，免 API，用于列表/播报/估值）。详情卡用 `battle_scale_line`：查 `/battles/{id}` 整场人数（小规模≤6/小团≤30/团战≤80/ZvZ>80）显示「你队N人 整场M人 类别」+ 尖刀小队推测。
- **尖刀/炸弹小队启发式**（仅详情卡）：你队 `GroupMembers≤10` 且 整场 `players≥40` → 标「⚡尖刀/炸弹小队?(推测)」。`gi.battle(id)` 查询，失败回退队伍口径。
- **KOOK 卡片图片坑**：`Module.ImageGroup` 内 `Element.Image` 不能带 `size`（带 `sm` 会 40000 校验失败），用默认即可；外链图（官方渲染 `render.albiononline.com/v1/item/{id}.png?quality=N`）KOOK 服务端会抓取并缓存到自有 CDN，无需本地中转。`items.render_url()` 是图床方案的唯一改动点。
- **同 token 调试坑**：服务器 systemd 和本地开发不能同时使用同一个 `KOOK_TOKEN` 跑 bot，否则会抢 KOOK WebSocket/重复处理消息。2026-06-15 当前本地 `.env` 已临时改回线上旧 token，因此服务器必须保持 `systemctl stop albion-kook.service`；调完本地后再 `systemctl start albion-kook.service`。如果本地改回独立开发 bot token，才可以不停线上服务直接调试。启动日志会打印安全诊断 `bot_id/token_fp/token_source`，不要打印 token 原文。

## 进度

| 里程碑 | 状态 |
|---|---|
| 规划 + 接口实测 | ✅ 完成 |
| M0 脚手架（khl.py 连 WS + /ping） | ✅ 已运行 |
| M1 数据层 | ✅ 完成，真实 API 端到端跑通 |
| M2 公会绑定 | ✅ 完成，活测通过（搜索→会长/联盟卡片→按钮→落库） |
| M3 玩家绑定+审批 | ✅ 已活测：真实 KOOK 审批卡/结果卡、真实 Albion 搜索、发组和昵称同步通过；测试用户昵称恢复被 KOOK 限流，待稍后重试 |
| M4 查询指令 | ✅ 代码完成，6 指令数据对真实 API 全通 |
| M5 补装 | ✅ 已扩展：补装中心四频道、审核身份组、待发放/已发放、背包不计补装 |
| M6 自动任务（播报+退会复查） | ✅ 已运行：全局 feed 双向筛、价格参考库定时刷新 |
| AI 辅助首发 | ✅ 已运行：LongCat 探针通过，`/助手` 和 `/战报` 核心路径实测通过，AI 只读边界有单测 |
| AI 只读查询增强 + 高频露出 | ✅ 已实现：绑定状态、最近击杀/阵亡、补装队列、管理员配置概况、补装审核卡 AI 提示、自动战报卡 AI 摘要，含危险输出拦截和密钥脱敏 |
| 版本号控制 | ✅ 已实现：当前版本 `1.0`，`/ping` 带版本号，有单测 |
| 战报聚合/自动推送 | ✅ 已实现模块、单测、战报频道配置、定时推送代码路径和持久去重；本机真实 KOOK 发送路径已确认频道路由和去重，线上自动窗口待观察 |
| M7 出勤快照 | ⏸ 后置，等用户反馈确认考勤口径 |

### M3-M6 验证记录（2026-06-14）
- M4：armskey/muaowo 不在 Mika；用 Mika Top 成员验：战绩(KD/近战)、估值(luge666 153万)、榜单(Top10)、物价(老手级双剑反查)、金价(12446)、战役(3条) 全通。
- M5：估值路径复用 valuation，对真实死亡事件出值正常；补装审批通过前会重新估值，`approved` 后可继续标记 `paid`。
- M6：全局 feed 双向筛实证抓到本会击杀+阵亡；去重稳定。
- 离线全量编译通过；线上 bot 已带 M3-M6 和补装口径修复重启。
- 2026-06-14 文档同步：`README.md` 重写为当前项目入口，新增 `使用说明书.md`。

## 待复测清单（用户回来测）

在测试服（`4676167053713576`，已绑 Mika，会员组=老兵）复测时必须使用 `asia-` 前缀频道；当前审批频道为 `asia-✅绑定审批` `6280501542155342`，旧 `审批测试` 已删除：
1. **M3 /绑定**：核心链路已用 `BEISHENGS 北笙` 活测通过；后续可再发 `/绑定 <Mika成员名> [自定义昵称]` 复测普通用户体验。再测不在 Mika 的角色（如 armskey）应被拒。`/解绑` 撤组。
   - 前置：bot 身份组要**高于**「老兵」且有「管理身份组」「修改他人昵称」权限，否则发组/改名会失败（有告警提示）。
2. **M4**：`/战绩 <名>`、`/估值 <名>`、`/榜单 pvp`、`/榜单 pve`、`/物价 老手级双剑`、`/金价`、`/战役`。
3. **M5 /补装**：先 `/设置 补装审核身份组 @身份组`，再 `/设置 补装初始化频道` 新建或复用 `asia-🛡️补装中心` 四频道（或手动绑定 `#asia-📥补装申请`、`#asia-🔍补装审核`、`#asia-💰补装发放`、`#asia-📣补装通知`）→ 普通成员 `/补装审核` → `asia-✅绑定审批` 出身份申请卡 → 管理员点[通过] 自动发组 → 该成员可测 `/补装 待处理`、`/补装 待发放`、`/补装 列表` 与补装卡 [通过]/[拒绝]/[标记已发放]。补装申请侧：/绑定 自己 → 在 `asia-📥补装申请` 频道 `/补装` → 点 [详情] 看装备明细+击杀板链接，或 [选这个补装] → `asia-🔍补装审核` 出审核卡 → [通过] → `asia-💰补装发放` 出「待发放」卡 → 发放后点 [标记已发放] → `asia-📣补装通知` 只发完成 @；成员可 `/补装状态` 查进度。
4. **M6 播报/成员变动**：配置 `#asia-📢成员变动`、`#asia-⚔️击杀播报`、`#asia-💀阵亡播报`、`#asia-🗺️战报推送` 后复测；普通时段等 4 分钟、20:00-00:30 等 90 秒，有 Mika 击杀/阵亡会推卡片；击杀/死亡声望大于 100 万，或银币总损失大于 1000 万时大额高亮。退会复查是每日 4 点 cron，通知发成员变动频道。

## 下一步

先重试恢复测试用户 `1380312587` 的 KOOK 昵称为 `BEISHENGS`，然后继续 AI 只读查询打磨。M7 出勤暂不推进；等真实用户反馈“现在考勤怎么算”后，再决定 `/出勤` 是否用 `/battles?guildId=` + `/events/battle/{id}` 聚合最近 N 场参战者，或另做采集器/趋势版。
