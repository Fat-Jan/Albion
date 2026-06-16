# 阿尔比恩公会 KOOK 机器人

面向《Albion Online》亚服公会的 KOOK 机器人。项目把公会绑定、成员自助绑定、战斗查询、死亡播报、补装审批和市场估值集中到一个轻量 Python 服务里，运行数据使用本地 SQLite 保存。

GitHub 仓库：<https://github.com/Fat-Jan/Albion.git>

详细操作手册见 [使用说明书.md](使用说明书.md)。设计过程见 [KOOK 机器人实现计划.md](KOOK机器人实现计划.md)，数据源说明见 [阿尔比恩数据接口文档.md](阿尔比恩数据接口文档.md)。

## 项目状态

- 当前通用版本为 `1.0`，单一来源为 `bot/version.py`；机器人在线时 `/ping` 返回 `pong v1.0`。
- 默认面向亚服：官方战斗数据走 `gameinfo-sgp`，市场数据走 AODP `east`，ZvZ 战报走 albionbb `asia`。
- 一个 KOOK 服务器绑定一个 Albion 公会；公会、成员、频道、身份组、补装和战报去重状态保存在本地 SQLite。
- 频道配置保存的是 KOOK 频道 ID，不依赖频道名称。手动改频道名通常不影响机器人；删除频道、重建频道或迁移到新服务器后，需要重新执行对应 `/设置 ...频道 #频道`。
- 补装金额只计算穿戴装备；背包物品只在详情和总损失里展示，不计入补装。
- 武器/副手低价参考库覆盖 T4-T8、附魔 `@1`-`@4`、品质 1-5，每 3 天自动刷新。
- AI 默认关闭；开启后会出现在 `/战报`、`/助手`、`/补装解释`、补装审核卡和自动 ZvZ 战报卡，但仍只做只读摘要和解释。
- ZvZ 战报聚合、专属频道配置、最小本会参战人数阈值、持久去重和自动定时推送代码路径已有离线测试覆盖；开启 AI 后，自动推送卡会附带 AI 摘要。
- 当前部署实例、活测证据和具体公会相关运维事实只记录在 `STATUS.md` 与 `notepad.md`，不写入通用 README。
- 项目采用轻量 harness：接手入口见 `AGENTS.md`，短状态见 `STATUS.md`，离线门禁见 `scripts/check.sh`。

## 功能概览

### 公会与成员绑定

- `/绑定公会 <公会名>`：管理员把当前 KOOK 服务器绑定到 Albion 公会。
- `/设置 会员身份组 @身份组`：配置绑定通过后发放的会员身份组。
- `/设置 审批频道 #频道`：配置绑定审批和补装审核身份申请频道。
- `/设置 补装初始化频道`：自动新建 `🛡️补装中心` 分组和四个补装频道，并写入配置。
- `/设置 播报频道 #频道`：配置旧版统一播报频道，也作为击杀/阵亡频道未单独配置时的兜底。
- `/设置 击杀播报频道 #频道`：配置我方击杀播报频道。
- `/设置 阵亡播报频道 #频道`：配置我方阵亡播报频道（也兼容 `/设置 死亡播报频道 #频道`）。
- `/设置 战报推送频道 #频道`：配置 ZvZ 聚合战报专用频道（也兼容 `/设置 战报频道 #频道`）。
- `/设置 战报本会最小人数 <人数>`：配置自动战报推送的本会参战人数阈值，默认 20 人。
- `/设置 成员变动频道 #频道`：配置退会复查通知频道。
- `/设置 可信身份组 @身份组...`：配置可信成员组，满足条件时可快速通过绑定。
- `/绑定 <角色名> [自定义昵称]`：成员申请绑定 Albion 角色；可选自定义昵称会让 KOOK 昵称同步为 `角色名 - 自定义昵称`，例如 `BEISHENGS - 北笙`。
- `/解绑`：成员解除自己的角色绑定。

绑定关系仍然是一人一服一条记录；自定义昵称保存在 `player_binding.custom_nickname`，审批中的值保存在 `pending_approval.custom_nickname`，不会新增一条绑定行。绑定待审批卡会显示申请号、待审批状态和目标 KOOK 昵称。审批通过或拒绝后，机器人会把结果卡发到成员变动频道；未配置时兜底审批频道。结果卡包含绑定申请号、申请人、角色、目标 KOOK 昵称和当前状态，并会尽量把原审批卡原地更新为已通过或已拒绝。

频道设置写入的是 KOOK 频道 ID；只改频道名不需要重新配置，删除频道或重建频道后才需要重新 `/设置`。

### 查询指令

- `/战绩 [角色名]`：查看角色概况、最近击杀和最近阵亡。
- `/估值 [角色名]`：估最近一次死亡，拆分装备估值、背包估值和总损失。
- `/物价 <物品名或 ID>`：查亚服各城当前最低卖单。
- `/金价`：查最新金价。
- `/榜单 pvp|pve`：查当前绑定公会成员排行榜。
- `/战役`：查当前绑定公会最近 ZvZ 战役。
- `/战报 [日期]`：AI 基于最近战役生成短摘要；带日期时按北京时间 ZvZ 夜间窗口查询，例如 `/战报 6-15` 会统计 `2026-06-15 14:30` 到 `2026-06-16 05:00`。
- `/助手 <问题>`：AI 做命令引导和白名单只读查询，可查本人绑定状态、本人最近击杀/阵亡、本人补装进度；管理员/补装审核员可查补装队列概况，管理员可查频道配置概况。

### 补装流程

- `/设置 补装初始化频道`：推荐初始化方式，新建 `🛡️补装中心`、`📥补装申请`、`🔍补装审核`、`💰补装发放`、`📣补装通知`。
- `/设置 补装申请频道|补装审核频道|补装发放频道|补装通知频道 #频道`：手动绑定四个补装频道。
- `/设置 补装频道 #频道`：旧版单频道兜底；新流程不建议继续复用旧频道。
- `/设置 补装审核身份组 @身份组...`：配置可审批补装、标记发放的身份组。
- `/补装审核`：普通成员申请补装审核身份，管理员审批通过后自动发组。
- `/补装`：绑定成员查看最近死亡，点「详情」或「选这个补装」。
- `/补装状态`：成员查看自己的最近补装进度。
- `/补装 待处理|待发放|列表`：管理员或补装审核员查看补装队列。
- `/补装 拒绝 #申请号 理由文本`：管理员或补装审核员用自定义理由拒绝补装。
- `/补装 发放 #申请号 银币|装备|物品 [备注]`：管理员或补装审核员按发放方式标记补装完成。
- `/补装解释 <申请号>`：AI 基于事实包解释补装金额和异常点，不参与审批。

状态流转：

```text
pending（待审批） -> approved（待发放） -> paid（已发放）
pending（待审批） -> rejected（已拒绝）
```

审批通过前会按当前市场数据刷新补装金额。已落库的旧记录不会被静默重算。
审核频道、发放频道和补装通知卡会显示申请号、当前状态、死亡摘要、装备文字明细、补装金额和带事件号的官方击杀板链接；待审批卡也会显示申请号和待审批状态。开启 AI 时，待审批卡会附带「AI 审核提示」，只解释补装口径、缺价或异常点，不给通过/拒绝结论。通过、拒绝、发放都会在补装通知频道 @ 申请人，拒绝会记录原因，发放会记录处理时间和发放方式。数据库中的处理/审核/发放时间在 KOOK 卡片里统一显示为北京时间并标注。按钮处理后会尽量把原审核卡原地更新为已通过、已拒绝或已发放；如果 KOOK 消息更新失败，仍会发送新的状态通知。

补装审核身份申请也会在处理后发结果卡到成员变动频道，未配置时兜底审批频道；结果卡包含申请号、申请人、当前状态和北京时间审核时间，并会尽量更新原申请卡。

推荐频道结构：

```text
补装中心
├─ 补装申请      成员可见，可发 /补装 /补装状态
├─ 补装审核      仅补装组/管理可见
├─ 补装发放      仅补装组/发放组/管理可见
└─ 补装通知      成员可见，只发完成通知
```

### 自动任务

- 死亡播报：普通时段每 4 分钟轮询全局事件，20:00-00:30 每 90 秒，筛选本会击杀和阵亡；可分别推送到击杀播报和阵亡播报频道。
- 退会复查：每天 04:00 比对 Albion 公会成员，退会则撤 KOOK 会员组、删除绑定，并通知成员变动频道。
- 价格参考库刷新：每 3 天刷新 T4-T8 主手、双手、副手低价参考。
- ZvZ 战报推送：北京时间 14:30 到次日 05:00 每 15 分钟检查一次，命中绑定公会且达到本会参战人数阈值后推送专属战报卡；开启 AI 时，卡片会附带只读 AI 摘要。

## 技术栈

| 项目 | 说明 |
|---|---|
| 语言 | Python 3.11+，当前实测 Python 3.13.12 |
| KOOK SDK | khl.py，WebSocket 模式 |
| HTTP 客户端 | httpx |
| 存储 | SQLite |
| 战斗数据 | 官方 `gameinfo-sgp` |
| 市场数据 | Albion Online Data Project `east` |
| ZvZ 数据 | albionbb `asia` |

## 快速开始

### 1. 准备环境

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```dotenv
KOOK_TOKEN=
GAMEINFO_BASE=https://gameinfo-sgp.albiononline.com/api/gameinfo
AODP_BASE=https://east.albion-online-data.com
ALBIONBB_BASE=https://api.albionbb.com/asia
ALBIONBB_WEB_BASE=https://east.albionbb.com
KILLBOARD_SERVER=live_sgp
DISPLAY_TZ=Asia/Shanghai
DISPLAY_TZ_LABEL=北京时间
DISPLAY_TZ_SHORT_LABEL=北京
DB_PATH=data/bot.db
LOG_LEVEL=INFO
AI_ENABLED=false
AI_BASE_URL=https://api.longcat.chat/openai
AI_MODEL=LongCat-2.0-Preview
AI_API_KEY=
LONGCAT_API_KEY=
AI_TIMEOUT_SEC=20
AI_MAX_OUTPUT_TOKENS=800
```

`KOOK_TOKEN` 是必填密钥。启用 AI 时使用 `AI_API_KEY` 或 `LONGCAT_API_KEY`，前者优先。密钥不要提交到 Git。

欧服部署时保持北京时间显示和 `/战报 [日期]` 的北京时间窗口，只把区服数据源改成欧服：

```dotenv
GAMEINFO_BASE=https://gameinfo-ams.albiononline.com/api/gameinfo
AODP_BASE=https://europe.albion-online-data.com
ALBIONBB_BASE=https://api.albionbb.com/eu
ALBIONBB_WEB_BASE=https://europe.albionbb.com
KILLBOARD_SERVER=live_ams
DISPLAY_TZ=Asia/Shanghai
DISPLAY_TZ_LABEL=北京时间
DISPLAY_TZ_SHORT_LABEL=北京
```

### 3. 初始化数据库

```bash
.venv/bin/python -m bot.store.db
```

### 4. 启动机器人

前台运行：

```bash
.venv/bin/python -m bot.main
```

后台运行：

```bash
nohup .venv/bin/python -m bot.main > bot.log 2>&1 &
```

## 运维命令

同一个 `KOOK_TOKEN` 不能被两个正在运行的 bot 进程同时使用，否则会抢 KOOK WebSocket 连接并可能重复处理消息。调试线上同一个 bot token 前，先停止线上服务：

```bash
systemctl stop albion-kook.service
.venv/bin/python -m bot.main
systemctl start albion-kook.service
```

如果本地 `.env` 使用独立开发 bot token，则可以直接启动本地机器人调试，不需要停止线上服务：

```bash
.venv/bin/python -m bot.main
```

启动日志会打印安全诊断 `bot_id/token_fp/token_source`，用来确认实际生效 token；不要在日志、提交或汇报中输出 token 原文。

如果用 systemd 托管，可按自己的部署路径创建服务后使用：

```bash
systemctl status albion-kook.service --no-pager --lines=80
systemctl restart albion-kook.service
journalctl -u albion-kook.service -n 100 --no-pager
tail -80 /var/log/albion-kook/bot.log
```

查看 bot 进程：

```bash
ps -ef | rg '\.venv/bin/python -m bot\.main|python -m bot\.main'
```

停止 bot：

```bash
kill <PID>
```

查看日志：

```bash
tail -80 bot.log
```

查看数据库概况：

```bash
sqlite3 data/bot.db ".tables"
sqlite3 data/bot.db "select status, count(*) from regear_request group by status;"
sqlite3 data/bot.db "select count(*) from market_price_reference;"
```

手动刷新武器/副手低价参考库：

```bash
.venv/bin/python -m scripts.refresh_price_reference
```

清理补装记录前建议先备份：

```bash
mkdir -p data/backups
cp data/bot.db "data/backups/bot-before-regear-clean-$(date +%Y%m%d-%H%M%S).db"
sqlite3 data/bot.db "delete from regear_request; delete from regear_reviewer_request; vacuum;"
```

## 测试

推荐统一入口：

```bash
scripts/check.sh
```

等价命令：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall bot scripts tests
```

这只是离线门禁，不会启动 KOOK bot。涉及真实 KOOK 交互、systemd、数据库清理或外部 API 实测时，需要另行记录活测证据。

## 数据口径

### 估值

估值优先级：

1. 红城近 7 天历史均价中位数。
2. 多城近 7 天历史均价中位数。
3. 同物品其他品质历史价或当前挂单价，并按 0.85 折扣。
4. 本地武器/副手低价参考库。
5. 仍无数据时显示无市场价。

当前挂单价只作为兜底。主手、双手、副手如果命中本地低价参考库，且实时挂单兜底价高于参考价 3 倍以上，会按参考价封顶，避免低频装备被单个天价挂单污染补装估值。

补装金额只累加穿戴槽位：

- MainHand
- OffHand
- Head
- Armor
- Shoes
- Bag
- Cape
- Mount
- Potion
- Food

Inventory 背包物品不计入补装金额。

### 死亡地点

官方公开 API 当前不稳定提供真实死亡地图。项目已去掉地点展示，只保留时间、IP、规模、装备估值和击杀板链接。

## 安全边界

- `.env`、SQLite 数据库、日志和备份目录默认不提交。
- KOOK Token 只放本机 `.env`。
- 补装审批、发放状态和身份组变更必须由规则和管理员点击确认控制。
- 不建议让 AI 自动批准绑定、自动批准补装、改写补装金额或撤销身份组。

## AI 辅助

AI 走 LongCat/OpenAI 兼容接口，默认关闭。开启后可用 `/战报 [日期]`、`/助手 <问题>`、`/补装解释 <申请号>`，并会自动出现在补装审核卡和自动 ZvZ 战报卡里。

AI 只作为辅助说明层：可以总结战斗记录、解释补装异常、生成新手命令引导、回答白名单只读查询。`/战报` 默认总结最近战役；`/战报 6-15`、`/战报 6月15`、`/战报 2026-06-15` 会按北京时间目标日 14:30 到次日 05:00 的 ZvZ 夜间窗口过滤战役。`/助手` 当前白名单包括本人绑定状态、本人最近击杀/阵亡、本人补装进度、补装队列概况（管理员/补装审核员）和频道配置概况（管理员）。自动 ZvZ 战报摘要只基于战报事实包生成，补装审核提示只基于补装申请和估值事实包生成。

所有 AI 查询都只接收结构化事实包，不给模型任意查库或写库能力；输出层会拦截“已批准、已发组、已改金额、已标记发放”等危险动作声明，并对疑似 Token/API Key 文本脱敏。补装金额、绑定权限、审批、发放状态和身份组变更仍由规则、数据库和管理员点击控制。

## 项目结构

```text
bot/
  albion/      Albion API、市场数据、物品字典、估值逻辑
  cards/       KOOK 卡片渲染
  commands/    指令注册和交互流程
  store/       SQLite schema 和 repository
  tasks/       定时任务
scripts/       物品字典构建、价格参考库刷新、烟测脚本
tests/         单元测试
```

## 许可证

MIT。详见 [LICENSE](LICENSE)。
