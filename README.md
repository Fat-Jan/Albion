# 阿尔比恩公会 KOOK 机器人

面向《Albion Online》亚服公会的 KOOK 机器人。项目把公会绑定、成员自助绑定、战斗查询、死亡播报、补装审批和市场估值集中到一个轻量 Python 服务里，运行数据使用本地 SQLite 保存。

GitHub 仓库：<https://github.com/Fat-Jan/Albion.git>

详细操作手册见 [使用说明书.md](使用说明书.md)。设计过程见 [KOOK 机器人实现计划.md](KOOK机器人实现计划.md)，数据源说明见 [阿尔比恩数据接口文档.md](阿尔比恩数据接口文档.md)。

## 当前状态

- M0-M6 已实现并在线运行，入口为 `.venv/bin/python -m bot.main`。
- 当前只保留一个 bot 进程；最近整理后进程 PID 为 `20891`。
- SQLite 已保存公会绑定、玩家绑定、武器/副手价格参考库。
- 旧补装测试记录已清空，清理前数据库备份在 `data/backups/`（不提交到 Git）。
- 补装金额只计算穿戴装备；背包物品只在详情和总损失里展示，不计入补装。
- 武器/副手低价参考库覆盖 T4-T8、附魔 `@1`-`@4`、品质 1-5，每 3 天自动刷新。
- 下一阶段主要是 M7 出勤快照，以及继续做 KOOK 端活测收口。

## 功能概览

### 公会与成员绑定

- `/绑定公会 <公会名>`：管理员把当前 KOOK 服务器绑定到 Albion 公会。
- `/设置 会员身份组 @身份组`：配置绑定通过后发放的会员身份组。
- `/设置 审批频道 #频道`：配置绑定审批和补装审核身份申请频道。
- `/设置 可信身份组 @身份组...`：配置可信成员组，满足条件时可快速通过绑定。
- `/绑定 <角色名>`：成员申请绑定 Albion 角色。
- `/解绑`：成员解除自己的角色绑定。

### 查询指令

- `/战绩 [角色名]`：查看角色概况、最近击杀和最近阵亡。
- `/估值 [角色名]`：估最近一次死亡，拆分装备估值、背包估值和总损失。
- `/物价 <物品名或 ID>`：查亚服各城当前最低卖单。
- `/金价`：查最新金价。
- `/榜单 pvp|pve`：查当前绑定公会成员排行榜。
- `/战役`：查当前绑定公会最近 ZvZ 战役。

### 补装流程

- `/设置 补装频道 #频道`：配置独立补装申请和审批频道。
- `/设置 补装审核身份组 @身份组...`：配置可审批补装、标记发放的身份组。
- `/补装审核`：普通成员申请补装审核身份，管理员审批通过后自动发组。
- `/补装`：绑定成员查看最近死亡，点「详情」或「选这个补装」。
- `/补装 待处理|待发放|列表`：管理员或补装审核员查看补装队列。

状态流转：

```text
pending（待审批） -> approved（待发放） -> paid（已发放）
pending（待审批） -> rejected（已拒绝）
```

审批通过前会按当前市场数据刷新补装金额。已落库的旧记录不会被静默重算。

### 自动任务

- 死亡播报：每 2 分钟轮询全局事件，筛选本会击杀和阵亡。
- 退会复查：每天 04:00 比对 Albion 公会成员，退会则撤 KOOK 会员组并删除绑定。
- 价格参考库刷新：每 3 天刷新 T4-T8 主手、双手、副手低价参考。

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
DB_PATH=data/bot.db
LOG_LEVEL=INFO
```

`KOOK_TOKEN` 是必填密钥，不要提交到 Git。

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

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall bot scripts tests
```

## 数据口径

### 估值

估值优先级：

1. 红城近 7 天历史均价中位数。
2. 多城近 7 天历史均价中位数。
3. 同物品其他品质历史价或当前挂单价，并按 0.85 折扣。
4. 本地武器/副手低价参考库。
5. 仍无数据时显示无市场价。

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

## AI 使用建议

当前阶段不需要把 AI 接入正式审批链路。补装金额、绑定权限和发放状态都需要可解释、可复核、可落库，规则和市场数据已经足够覆盖主流程。

适合后续引入 AI 的方向：

- 总结战斗记录、生成周报和补装复盘。
- 帮管理员解释异常补装，例如装备缺价、背包金额较高、审批金额变化。
- 给新人生成命令引导。
- 做自然语言查询，例如「查一下 Latano 最近三次阵亡和补装状态」。

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
