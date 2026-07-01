# M7 出勤与前端数据面板实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把 M7 出勤从“最近 N 场战斗参与快照”开始落地，并为后续前端状态面板、通用实时数据、长期采集和正式 CTA 出勤系统铺好边界。

**架构：** 第一阶段不做正式 CTA 考勤，只复用官方 gameinfo 的 guild members、guild battles、battle detail 和 battle events，生成可解释的“战斗参与快照”。第二阶段把快照结果持久化到 SQLite，供 KOOK 命令和前端共享。前端只读展示后端缓存与 bot 健康状态，不直接打 Albion 外部 API，不触碰 KOOK 密钥。

**技术栈：** Python 3.11+/3.13、khl.py、httpx、SQLite、unittest、compileall；前端建议独立轻量 Web UI（FastAPI/Starlette + 静态 HTML 或后续 React 均可），第一版优先从 Python 进程暴露只读 JSON。

---

## 0. 调研结论和范围切分

### 外部参考

- Albion Online Tools Discord Bot 常见功能：服务器状态、物价、玩家统计、公会统计、金币/会员价格、装备图片、Killboard 追踪通知、阵营战、Avalonian Roads、添加 bot 按钮。
- AO Master 的正式出勤模型：CTA 事件、报名窗口、开团时间、上传窗口、队长上传队伍截图、OCR、去重、人工修正、赛季汇总。
- AODP 市场 API 适合价格/金币数据，欧服使用 `https://europe.albion-online-data.com`，采集必须做缓存和限流。
- `https://www.aerbien.com/#` 当前更适合作为中文社区/导航/补丁内容参考，没有纳入核心结构化数据源。

### 不做的事情

- M7 第一版不声称“正式考勤”，只叫“战斗参与快照”。
- M7 第一版不做 OCR、队伍截图识别、请假、奖惩、补贴资格自动判定。
- 前端第一版不提供后台写操作，不做绑定审批、补装审批、发组、撤组、改金额或标记发放。
- 不从 aerbien 做非授权结构化爬取；除非后续确认有公开稳定 API 或明确允许的 RSS/JSON。

### 优先度排序原则

后续开发按业务价值和依赖关系做优先度排序，不按“看起来功能多”推进：

| 优先级 | 阶段 | 说明 | 暂缓原因 |
|---|---|---|---|
| P0 | M7a `/出勤` 快照 | 先给 KOOK 用户一个能解释的最近 N 场参与结果 | 无需新前端、无需长期采集器 |
| P1 | M7b 持久化 + M8a 只读 API | 把快照变成 bot 和前端可共用的数据事实 | 是前端和趋势展示的前置依赖 |
| P2 | M8b 前端 + M8c 数据采集扩展 | 展示 bot 状态、邀请按钮、榜单、高声望事件和出勤快照 | 依赖 P1 的只读 API 和缓存表 |
| P3 | M9 正式 CTA 出勤 | 报名、确认、补录、赛季统计 | 需要公会先确认正式考勤规则 |

展示层也按优先度排序，不做无限长榜：
- `/出勤` 默认按“参与场数多、最近参战更近、角色名稳定排序”展示，优先显示 Top 参与成员和低参与/未参与成员摘要。
- 前端榜单默认展示 Top 20，可配置到 Top 50；需要全量导出时另做管理导出，不在第一版页面无限滚动。
- 高声望事件按事件时间倒序和声望/损失阈值排序，只展示最近窗口内命中的事件。
- 正式 CTA 统计上线前，任何排序结果都标注为“战斗参与快照”，不作为奖惩自动依据。

### 子系统归属

| 优先级 | 阶段 | 主要归属 | 内容 | 对用户可见形态 |
|---|---|---|---|---|
| P0 | M7a | Bot + 后端服务层 | `/出勤` 最近 N 场战斗参与快照 | KOOK 命令卡片/文本 |
| P1 | M7b | 后端数据层 + Bot 定时任务 | 成员、战斗、参与记录持久化 | KOOK 查询更快，前端可读 |
| P1 | M8a | 后端只读 API | bot 健康、配置摘要、缓存数据接口 | 前端 JSON 数据源 |
| P2 | M8b | 前端 | bot 在线状态、添加 bot 按钮、实时数据页 | Web 面板 |
| P2 | M8c | 后端采集任务 | 高声望击杀/阵亡、PvE/PvP 榜单、金币/市场快照 | 前端榜单和趋势 |
| P3 | M9 | Bot + 后端 + 前端 | 正式 CTA 事件、报名、确认、赛季汇总 | KOOK 按钮 + 管理页 |

## 1. 推荐里程碑

### M7a：最近 N 场战斗参与快照

**归属：Bot 命令 + 后端纯计算。**

成功标准：
- 管理员或普通成员可以在 KOOK 使用 `/出勤` 查询绑定公会最近 N 场符合阈值的战斗参与情况。
- 默认 N 为 20，可传 5-50；默认只统计本会参战人数达到 20 的战斗，沿用自动战报最低阈值。
- 输出明确写“战斗参与快照，不等同正式 CTA 考勤”。
- 当前公会成员没有出现在最近战斗里的也显示为 0，避免只列活跃成员。

建议口径：
- 数据源：`GameInfo.guild_members(guild_id)` + `GameInfo.battles(guild_id=...)` + `GameInfo.battle(battle_id)`。
- 参与判定：battle detail 的 `players` 中 `guildId == 当前绑定公会 id`。
- 统计字段：成员名、参与场数、参与率、最近参与时间、击杀、死亡、killFame。
- 过滤条件：战斗详情中本会玩家数小于阈值则不计入；无法拉取详情的战斗跳过并记录 warning。

### M7b：持久化出勤快照和趋势

**归属：后端数据层 + Bot 定时任务。**

成功标准：
- SQLite 中保存 battle snapshot、participant rows、guild member snapshot。
- `/出勤` 优先读本地快照；缓存不足时再按 M7a 实时补拉。
- 可回答“近 7 天/30 天参与趋势”“连续未参与”“最近一次参战”。

建议口径：
- 成员快照每天 1-2 次。
- 战斗快照在 ZvZ 活跃窗口内 3-5 分钟一次，非活跃窗口 30-60 分钟一次。
- 单场 battle detail 按 battle id 幂等写入。

### M8：前端状态和实时数据面板

**归属：前端 + 后端只读 API。**

成功标准：
- 第一屏展示 EU/ASIA 两个 bot 的在线状态、最后心跳、版本、运行来源、最近自动任务时间。
- 提供“添加欧服 bot 到 KOOK”“添加亚服 bot 到 KOOK”两个按钮，邀请链接由配置提供，不在前端硬编码密钥。
- 展示通用只读数据：金币价格、PvP/PvE 榜单、高声望击杀/阵亡、Top Squad 最近战斗、出勤快照。
- 前端不直接读取 `.env`、SQLite 文件或外部 Albion API；只读后端 JSON。

### M9：正式 CTA 出勤系统

**归属：Bot 命令/按钮 + 后端数据层 + 前端管理页。**

触发条件：
- 公会明确需要“活动级考勤”“报名/请假/豁免”“按赛季奖惩或补贴资格”。

建议模型：
- `cta_event`：活动名称、开始时间、报名窗口、确认窗口、状态、创建人。
- `cta_signup`：报名人、角色名、队伍/职责、报名时间、取消时间。
- `cta_attendance`：活动 id、成员 id、来源（按钮确认/管理员补录/战斗快照辅助）、状态。
- `cta_adjustment`：人工修正、原因、操作人、时间。
- `cta_season`：赛季窗口、统计规则、归档状态。

第一版做法：
- KOOK 活动卡提供报名/取消报名/到场确认按钮。
- 管理员可手动补录/移除。
- 战斗快照只做辅助证据，不自动判罚。

## 2. 数据源和采集节奏

| 数据 | 来源 | 采集频率 | 存储 | 用途 |
|---|---|---:|---|---|
| 公会成员 | `gameinfo-ams /guilds/{id}/members` | 每日 1-2 次 | `guild_member_snapshot` | 出勤分母、退会参考、成员趋势 |
| 近期战斗 | `gameinfo-ams /battles?guildId=` | 活跃窗口 3-5 分钟 | `battle_snapshot` | 自动战报、出勤、前端最近战斗 |
| 战斗详情 | `gameinfo-ams /battles/{id}` | battle id 首次出现时 | `battle_participant` | 出勤、战报高光 |
| 战斗事件 | `gameinfo-ams /events/battle/{id}` | battle id 首次出现时 | `battle_event_snapshot` | 高光击杀/死亡、战报明细 |
| 高声望击杀/阵亡 | 现有全局 `/events` 多页轮询 | 60-90 秒 | `high_fame_event` | 播报、前端实时事件 |
| PvE/PvP 榜单 | `players/statistics`、`events/playerfame` | 6-24 小时 | `fame_leaderboard_snapshot` | 前端榜单、KOOK `/榜单` 加速 |
| 金币价格 | AODP `/api/v2/stats/gold.json` | 5-15 分钟 | `gold_price_snapshot` | 前端市场页、KOOK `/金价` |
| 市场价格 | AODP `/api/v2/stats/prices` | 按 item 批量，低频 | 现有 `market_price_reference` 或新增快照表 | 估值、热门物价 |

限流原则：
- AODP 遵守 `180/min` 与 `300/5min`，批量 item 查询，避免逐 item 请求。
- gameinfo 没有可靠公开硬限流表，按缓存头和现有 ttl 走，失败时退避。
- 所有采集必须幂等，重复执行不能重复写脏数据。

## 3. 文件结构规划

### 后端/Bot 共享计算

- 创建：`bot/albion/attendance.py`
  - 纯计算模块：把成员列表、battle rows、battle details 转成参与快照。
- 创建：`bot/cards/attendance_cards.py`
  - 渲染 `/出勤` KOOK 卡片或文本片段。
- 修改：`bot/commands/query.py`
  - 注册 `/出勤` 命令，解析最近 N 场和可选玩家名。
- 修改：`bot/albion/gameinfo.py`
  - 如现有方法不够，只补小型封装；优先复用 `guild_members`、`battles`、`battle`、`battle_events`。
- 创建：`tests/test_attendance.py`
  - 覆盖参与统计、阈值过滤、缺席成员、异常战斗跳过、命令参数边界。

### 后端数据层和采集

- 修改：`bot/store/db.py`
  - 增加幂等迁移：出勤、榜单、健康状态、采集游标所需表。
- 修改：`bot/store/repo.py`
  - 增加出勤快照、事件快照、榜单快照读写方法。
- 修改：`bot/tasks/auto.py`
  - 增加低频 collector 注册，复用现有 APScheduler 入口。
- 创建：`bot/tasks/collectors.py`
  - 把出勤、榜单、金币、事件采集逻辑从 `auto.py` 拆出，避免 `auto.py` 继续膨胀。
- 创建：`tests/test_collectors.py`
  - 覆盖幂等写入、采集失败退避、不重复写 battle/event。

### 只读 Web API

- 修改：`bot/main.py`
  - 扩展现有 health server，或挂载新的只读 JSON 路由。
- 创建：`bot/web/status_api.py`
  - 输出 `/healthz`、`/api/status`、`/api/leaderboards`、`/api/events/high-fame`、`/api/attendance/recent`。
- 创建：`tests/test_status_api.py`
  - 覆盖 JSON schema、敏感字段不外泄、无数据库数据时返回空列表而不是 500。

### 前端

第一版建议先创建静态前端，避免过早引入复杂构建：
- 创建：`web/index.html`
- 创建：`web/styles.css`
- 创建：`web/app.js`

如果后续需要复杂交互，再升级为 React/Vite：
- 创建：`web/package.json`
- 创建：`web/src/App.tsx`
- 创建：`web/src/api.ts`

第一版页面模块：
- Bot 状态：EU/ASIA、最后心跳、版本、运行环境、最近任务时间。
- 添加 bot：欧服/亚服 KOOK 邀请按钮。
- 实时事件：高声望击杀/阵亡列表。
- 榜单：PvP/PvE 切换。
- 出勤：最近 N 场参与快照，默认只读展示。

### 配置

- 修改：`bot/config.py`
  - 增加 `WEB_PUBLIC_BASE_URL`、`KOOK_INVITE_URL_EU`、`KOOK_INVITE_URL_ASIA`、collector 开关和频率。
- 修改：`.env.example`
  - 只写变量名和示例，不写真实 token。

## 4. 任务分解

### 任务 1：实现 M7a 纯计算核心

**归属：后端/Bot 共享计算。**

**文件：**
- 创建：`bot/albion/attendance.py`
- 创建：`tests/test_attendance.py`

- [x] **步骤 1：写失败测试**

测试用例：
- 成员 A/B/C，battle 1 有 A/B，battle 2 有 A，C 从未参与。
- 阈值为 2 时 battle 1 计入，battle 2 不计入。
- 结果中 C 仍存在，参与场数为 0。

运行：

```bash
.venv/bin/python -m unittest tests.test_attendance -v
```

预期：因为 `bot.albion.attendance` 尚未创建而失败。

- [x] **步骤 2：实现数据结构和统计函数**

建议函数：

```python
def build_attendance_snapshot(
    *,
    guild_id: str,
    members: list[dict],
    battle_details: list[dict],
    min_guild_players: int = 20,
) -> dict:
    ...
```

返回结构包含：
- `guild_id`
- `battle_count`
- `counted_battle_count`
- `min_guild_players`
- `members`
- `skipped_battles`

- [x] **步骤 3：运行目标测试**

```bash
.venv/bin/python -m unittest tests.test_attendance -v
```

预期：通过。

- [x] **步骤 4：运行全量门禁**

```bash
scripts/check.sh
```

预期：单元测试和 compileall 通过。

### 任务 2：接入 `/出勤` KOOK 命令

**归属：Bot 命令 + 卡片。**

**文件：**
- 修改：`bot/commands/query.py`
- 创建：`bot/cards/attendance_cards.py`
- 修改：`tests/test_query_cards.py` 或创建 `tests/test_attendance_cards.py`

- [x] **步骤 1：写卡片渲染测试**

覆盖：
- 标题包含“战斗参与快照”。
- 说明包含“不等同正式 CTA 考勤”。
- 成员列表显示参与场数和参与率。

运行：

```bash
.venv/bin/python -m unittest tests.test_attendance_cards -v
```

预期：失败，因为卡片模块尚未创建。

- [x] **步骤 2：实现出勤卡片**

卡片内容建议：
- 摘要：统计最近 N 场，计入 M 场，阈值 X 人。
- Top 参与成员。
- 低参与/未参与成员。
- 数据口径提示。

- [x] **步骤 3：写命令解析测试**

覆盖：
- `/出勤` 默认最近 20。
- `/出勤 10` 最近 10。
- `/出勤 60` 被限制到 50。
- 未绑定公会时给出绑定提示。

- [x] **步骤 4：实现命令**

流程：
1. 读取 `repo.get_guild_binding(kook_guild_id)`。
2. 拉 `gi.guild_members(guild_id)`。
3. 拉 `gi.battles(guild_id=guild_id, limit=n)`。
4. 对 battle id 拉 `gi.battle(id)`。
5. 调用 `build_attendance_snapshot()`。
6. 发送 `attendance_card()`。

- [x] **步骤 5：验证**

```bash
.venv/bin/python -m unittest tests.test_attendance tests.test_attendance_cards -v
scripts/check.sh
```

预期：全部通过；本步骤不启动真实 bot。

### 任务 3：增加出勤持久化表

**归属：后端数据层。**

**文件：**
- 修改：`bot/store/db.py`
- 修改：`bot/store/repo.py`
- 创建：`tests/test_attendance_store.py`

- [x] **步骤 1：写迁移测试**

验证新库初始化后存在：
- `guild_member_snapshot`
- `battle_snapshot`
- `battle_participant`
- `collector_cursor`

运行：

```bash
.venv/bin/python -m unittest tests.test_attendance_store -v
```

预期：失败，因为表未创建。

- [x] **步骤 2：实现幂等 schema**

建议唯一键：
- `guild_member_snapshot(kook_guild_id, albion_guild_id, captured_at, albion_player_id)`
- `battle_snapshot(battle_id)`
- `battle_participant(battle_id, albion_player_id)`
- `collector_cursor(name, kook_guild_id)`

- [x] **步骤 3：实现 repo 方法**

建议方法：
- `upsert_battle_snapshot(row: dict) -> None`
- `upsert_battle_participants(battle_id: str, rows: list[dict]) -> None`
- `save_guild_member_snapshot(...) -> None`
- `recent_attendance_snapshot(kook_guild_id: str, limit: int) -> dict`

- [x] **步骤 4：验证**

```bash
.venv/bin/python -m unittest tests.test_attendance_store -v
scripts/check.sh
```

预期：全部通过。

### 任务 4：增加出勤和榜单采集器

**归属：后端定时任务。**

**文件：**
- 创建：`bot/tasks/collectors.py`
- 修改：`bot/tasks/auto.py`
- 创建：`tests/test_collectors.py`

- [x] **步骤 1：写采集器测试**

覆盖：
- 同一个 battle id 重复采集只写一次。
- 单个 battle detail 拉取失败不会中断整轮。
- 没有配置 battle report channel 的公会也可以采集出勤数据，只要已绑定 Albion guild。

- [x] **步骤 2：实现 collectors**

建议函数：
- `collect_guild_members_once(gi, guild_binding)`
- `collect_recent_battles_once(gi, guild_binding, limit=20)`
- `collect_high_fame_events_once(gi, guild_binding)`
- `collect_fame_leaderboards_once(gi)`
- `collect_gold_price_once(market)`

执行备注：P1 先完成出勤所需的成员快照与近期战斗采集，并预留榜单/高声望事件 API 空表；P2 已补齐 `collect_high_fame_events_once`、`collect_fame_leaderboards_once` 和 `collect_gold_price_once`。

- [x] **步骤 3：接入 scheduler**

在 `bot/tasks/auto.py` 中注册：
- 成员快照：每日 1-2 次。
- 近期战斗：活跃窗口内 3-5 分钟一次。
- 榜单：6-24 小时。
- 金价：5-15 分钟。

- [x] **步骤 4：验证**

```bash
.venv/bin/python -m unittest tests.test_collectors -v
scripts/check.sh
```

预期：全部通过。

### 任务 5：只读 Web API

**归属：后端 API。**

**文件：**
- 创建：`bot/web/status_api.py`
- 修改：`bot/main.py`
- 创建：`tests/test_status_api.py`

- [x] **步骤 1：写 API 测试**

覆盖：
- `/api/status` 返回版本、region、last_heartbeat、last_task_run。
- `/api/status` 不返回 `KOOK_TOKEN`、`AI_API_KEY`、完整 token 指纹以外的密钥信息。
- 空库时 `/api/events/high-fame` 和 `/api/attendance/recent` 返回空数组。

- [x] **步骤 2：实现只读 API**

建议路由：
- `GET /healthz`
- `GET /api/status`
- `GET /api/invites`
- `GET /api/events/high-fame`
- `GET /api/leaderboards`
- `GET /api/market/gold`
- `GET /api/attendance/recent`

- [x] **步骤 3：验证**

```bash
.venv/bin/python -m unittest tests.test_status_api -v
scripts/check.sh
```

预期：全部通过。

### 任务 6：前端第一版

**归属：前端。**

**文件：**
- 创建：`web/index.html`
- 创建：`web/styles.css`
- 创建：`web/app.js`
- 创建：`tests/test_web_assets.py`

- [x] **步骤 1：写静态资源测试**

覆盖：
- `web/index.html` 引用 `styles.css` 和 `app.js`。
- 页面存在 EU/ASIA 邀请按钮容器。
- 页面没有写死真实 token 或 `.env` 值。

- [x] **步骤 2：实现页面结构**

第一屏模块：
- Bot 状态。
- 添加 bot 按钮。
- 最近任务。
- 高声望事件。
- 榜单。
- 出勤快照。

- [x] **步骤 3：实现 API 拉取**

`web/app.js` 从后端读取：
- `/api/status`
- `/api/invites`
- `/api/events/high-fame`
- `/api/leaderboards`
- `/api/market/gold`
- `/api/attendance/recent`

- [x] **步骤 4：浏览器验证**

启动本地服务后用浏览器检查：
- 桌面宽度 1440px。
- 移动宽度 390px。
- 文本不重叠，按钮不溢出，空数据状态清楚。

- [x] **步骤 5：验证**

```bash
.venv/bin/python -m unittest tests.test_web_assets tests.test_status_api -v
scripts/check.sh
```

预期：全部通过。

### 任务 7：正式 CTA 出勤设计落地

**归属：Bot + 后端 + 前端。**

执行前置：
- 已有真实公会反馈，确认需要按活动统计，而不是只看战斗参与。

**文件：**
- 创建：`bot/attendance/cta.py`
- 创建：`bot/cards/cta_cards.py`
- 修改：`bot/commands/query.py` 或创建 `bot/commands/attendance.py`
- 修改：`bot/store/db.py`
- 修改：`bot/store/repo.py`
- 修改：`web/index.html`、`web/app.js`
- 创建：`tests/test_cta_attendance.py`

- [ ] **步骤 1：写 CTA 数据模型测试**

覆盖：
- 创建活动。
- 报名/取消报名。
- 到场确认。
- 管理员手动补录。
- 人工修正有 audit row。

- [ ] **步骤 2：实现最小 CTA 模型**

表：
- `cta_event`
- `cta_signup`
- `cta_attendance`
- `cta_adjustment`
- `cta_season`

- [ ] **步骤 3：实现 KOOK 活动卡**

按钮：
- 报名。
- 取消报名。
- 到场确认。
- 管理员关闭活动。

- [ ] **步骤 4：前端增加 CTA 管理视图**

页面：
- 活动列表。
- 单活动报名/到场明细。
- 成员出勤率。
- 人工调整记录。

- [ ] **步骤 5：验证**

```bash
.venv/bin/python -m unittest tests.test_cta_attendance -v
scripts/check.sh
```

预期：全部通过；真实 KOOK 按钮活测需要单独记录到 `STATUS.md` 或 `notepad.md`。

## 4.1 执行记录

- 2026-06-24：已完成 P0/P1（任务 1-5）：`/出勤 [5-50]` 快照、出勤卡片、SQLite 成员/战斗/参与者/采集游标表、近期战斗与成员采集器、只读 Web API、配置示例和项目文档同步。未做任务 6 前端和任务 7 正式 CTA；榜单/高声望事件实际采集仍按 M8c/P2 后续推进。验证以 `STATUS.md` 最新记录为准。
- 2026-06-24：继续完成 P2（任务 4 的 M8c 扩展 + 任务 6）：新增高声望事件、PvP/PvE/声望榜和金价采集快照，新增 `/api/market/gold`，并交付静态 dashboard `/`、`/index.html`、`/styles.css`、`/app.js`。Chrome headless 已用 1440x900 和 390x844 访问临时只读服务生成截图；正式 CTA 出勤任务 7 未进入。验证以 `STATUS.md` 最新记录为准。

## 5. 验证门禁

每个后端/Bot 阶段至少运行：

```bash
scripts/check.sh
git diff --check
```

涉及前端页面时额外运行：

```bash
.venv/bin/python -m unittest tests.test_web_assets tests.test_status_api -v
```

涉及真实 KOOK 交互时：
- 不用 bot token 伪装真实用户。
- 先确认同一个 `KOOK_TOKEN` 没有本地和线上双开。
- 活测结果写入 `STATUS.md` 或 `notepad.md`，只写 token 指纹、bot_id、频道名/频道 id，不写 token 原文。

## 6. 优先度排序

1. **P0 / M7a `/出勤` 快照**：最小、最稳、马上能给公会反馈。
2. **P1 / M7b SQLite 快照**：把数据变成前端可读资产。
3. **P1 / M8a 只读 Web API**：让前端和 bot 共用同一数据事实。
4. **P2 / M8b 前端第一版**：状态、邀请按钮、通用实时数据。
5. **P2 / M8c 采集扩展**：榜单、金币、高声望事件趋势。
6. **P3 / M9 CTA 正式出勤**：等公会确认考勤规则后再做。

## 7. 自检

- 已区分前端、后端数据层、Bot 命令和定时任务。
- 已按 P0-P3 写清开发优先度和展示排序边界。
- M7 第一版没有过度承诺正式考勤。
- 前端不直接接触密钥或写操作。
- 数据采集有频率和限流边界。
- 每个阶段都有可运行验证命令。
- 计划不要求读取、输出、复制或提交 `.env` 密钥原文。
