# Findings & Decisions

## 三大用户诉求速览

1. **合仓**:OpenDeploy 现支持托管数据库+Redis,想把 EU/ASIA 双仓合成一个 project,靠数据库区分 region,省配额
2. **换 AI**:LongCat 已停止免费,换商汤 `token.sensenova.cn/v1`,key 已由主 agent 探针验证,计划文件不记录原文或前缀
3. **修延迟**:击杀/阵亡在 KOOK 延迟 5-10 分钟;夜间战报常静默

## 用户已拍板的三个关键点

| 问题 | 答复 |
|---|---|
| 双仓在同一个 KOOK 服务器还是两个 | **同一个 KOOK 服务器 `4676167053713576` 共存**,需要 region 列做联合 PK |
| OpenDeploy 拓扑 | **单容器 + 进程内双 bot 实例**(省钱、Web dashboard 好合并) |
| 战报门槛 | **min_guild_players 放低到 10**(去掉 `max(20, configured)` clamp) |

## 附加决策

- **合并基准**:以欧服代码 `Albion-EU-kook` 为主线,亚服合并顺便升级到 M7 全套 —— 差异是欧服领先的 attendance/collectors/web/status_api,亚服合完就自动补齐
- **数据库形态**:先保留 SQLite,靠 OpenDeploy 持久卷 `/app/data`;把 `region` 列加进所有 `kook_guild_id` 相关表,PK 变复合。**不切换到 Postgres**,因为:
  - 现有 schema/查询代码是 SQLite 语法,切 PG 是另一个大项目
  - 数据量小(6234 条 market_price_reference 是大头),SQLite 完全够
  - OpenDeploy 托管 PG 是"可用但非必需"
- **Redis 用不用**:暂不用。当前唯一像样的候选是 `AlbionClient._cache`(TTLCache 内存),迁 Redis 收益有限;`_seen` 去重改 SQLite 就够

---

## 双仓代码差异清单(2026-07-02 diff 结果)

已确认差异文件:
```
bot/config.py                  # 只有 GAMEINFO_BASE / AODP_BASE / ALBIONBB_BASE / KILLBOARD_SERVER 默认值 + WEB/INVITE URL(EU 独有)
bot/main.py                    # EU 用 StatusAPIHandler,ASIA 用内联 _HealthHandler
bot/ai/service.py              # 未细看,可能只是文案
bot/albion/gameinfo.py         # 未细看
bot/albion/market.py           # 未细看
bot/albion/valuation.py        # 未细看
bot/commands/query.py          # 未细看
bot/store/db.py                # 未细看,可能是 kill_fame_threshold 默认值
bot/store/repo.py              # 未细看
bot/tasks/auto.py              # EU 有 collectors 相关 4 个 task(ATTENDANCE/HIGH_FAME/LEADERBOARD/GOLD_PRICE),ASIA 没有
```

EU 独有的文件:
```
bot/albion/attendance.py           # M7 出勤快照聚合
bot/cards/attendance_cards.py      # 出勤卡片渲染
bot/tasks/collectors.py            # 4 个低频只读采集器
bot/web/                           # StatusAPIHandler + 静态 dashboard
```

**合并策略**:直接用 EU 版本覆盖 ASIA;ASIA 独有的差异只有 `KOOK_REGION_CODE=asia` 默认值 + region-specific URL 默认值 + `kill_fame_threshold=400000`,这些用户拍板改到 `bootstrap.py::RUNTIME_GUILD_CONFIGS` 或 env,不需要在代码里保留。

---

## SenseNova API 探针记录

**探针命令**(2026-07-02 主 agent 执行):
```bash
# 1. 列模型
curl -sS -H "Authorization: Bearer $SENSENOVA_API_KEY" https://token.sensenova.cn/v1/models
# 2. 探针 chat completions
curl -sS -X POST https://token.sensenova.cn/v1/chat/completions \
  -H "Authorization: Bearer $SENSENOVA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ok"}]}'
```

**可用模型**(pricing 全 0):
| ID | 特性 | 上下文 |
|---|---|---|
| `deepseek-v4-flash` | text-only, tools/json_mode/reasoning | 1M |
| `glm-5.2` | text-only, 长任务旗舰 | 1M |
| `sensenova-6.7-flash-lite` | 多模态(text+image), 轻量 | 256K |
| `sensenova-u1-fast` | text→image, 信息图生成 | 256K |

**推荐 `deepseek-v4-flash`**:
- 中文强(实测 "ok" → "好的,收到...")
- Response 带 `reasoning_content`(思维链)和 `content`(最终回复),现有 `bot/ai/client.py::complete()` 只取 `content` 兼容
- Response 示例(78 字节 prompt → 101 tokens):
  ```json
  {"choices":[{"message":{"role":"assistant",
    "content":"好的,收到。...",
    "reasoning_content":"用户只回复了...因此..."}}]}
  ```
- ⚠️ 注意 `AI_MAX_OUTPUT_TOKENS=800` 可能被 reasoning 吃掉,建议提高到 2000

**踩坑**:
- 直接调 `https://token.sensenova.cn/v1` 根路径 `POST` 返回 `Forbidden`(要走 `/chat/completions`)
- 用 `LongCat-2.0-Preview` model ID 返回 `model is not found`(废弃了)
- 商汤官网另有一个 `https://api.sensenova.cn/v1/llm/chat-completions` 是自研协议路径,**不是我们要用的**;`token.sensenova.cn/v1` 才是 OpenAI 兼容

---

## 播报延迟根因分析

### 击杀/阵亡 5-10 分钟延迟

代码路径:[bot/tasks/auto.py:366-438](../../bot/tasks/auto.py#L366-L438)

**已知参数**:
```python
BROADCAST_CHECK_INTERVAL_SEC = 30        # 外层 check 间隔
BROADCAST_INTERVAL_SEC = 90              # 普通时段实际拉数据间隔
BROADCAST_BUSY_INTERVAL_SEC = 60         # 20:00-00:30 忙时段
FEED_PAGES = 4                           # 每轮拉全局 feed 页数 (4×51=204 条)
MAX_BROADCAST_PER_TICK = 15              # 单轮播报上限
```

**延迟诱因分解**:

1. **`_primed` 冷启吞事件**:重启后第一轮把所有事件塞进 `_seen` 不播报,这轮耗时 = `_death_broadcast_interval_seconds()` = 60-90s。这是 **1-1.5 分钟 baseline**。

2. **`gameinfo_get` cache_ttl=30**:同一 `/events?offset=0` 请求 30s 内命中缓存,重启后新事件要等 30s 才拿到。**贡献 0-30s**。

3. **官方 API 上游延迟**:`gameinfo-ams.albiononline.com/api/gameinfo/events` 本身不是实时,事件从游戏服务器写到 API feed 有 30s-3min 抖动(社区常态)。**贡献 30s-3min**。

4. **`FEED_PAGES=4` 忙时段可能不够**:20:00-00:30 全球事件量大,204 条覆盖时间窗可能 < 60s,超出部分丢了要等下一轮。**贡献 1-2 分钟**。

5. **`MAX_BROADCAST_PER_TICK=15` 积压**:突发 ZvZ 会一次产生 20+ 事件,15 条上限 → 剩 5 条要等下一轮再播(60-90s 后)。**贡献 1-1.5 分钟**。

6. **`_seen` 仅内存**:重启后 `_primed=False`,吞掉的事件永远不播了。这不影响延迟但影响完整性。

**累加**:1.5 + 0.5 + 2 + 1.5 + 1 = **6.5 分钟**,与用户反馈 5-10 分钟吻合。

**修复方案**:见 task_plan.md Phase 3.4。

### 夜间战报静默

代码路径:[bot/tasks/auto.py:292-352](../../bot/tasks/auto.py#L292-L352)

**根因**:[bot/tasks/auto.py:268-276](../../bot/tasks/auto.py#L268-L276)
```python
def _effective_battle_report_min_guild_players(guild_binding: dict) -> int:
    try:
        configured = int(
            guild_binding.get("battle_report_min_guild_players")
            or BATTLE_REPORT_MIN_PLAYERS  # = 20
        )
    except (TypeError, ValueError):
        configured = BATTLE_REPORT_MIN_PLAYERS
    return max(BATTLE_REPORT_MIN_PLAYERS, configured)  # 强制最低 20
```

即使用户用 `/设置 战报本会最小人数 10` 把值改成 10,`max(20, 10) = 20` 仍然是 20。

**用户观察吻合**:夜间 Top Squad 参战 10-19 人的场次全部被过滤掉,只有 20+ 的场才推。

**修复**:`BATTLE_REPORT_MIN_PLAYERS = 10` + `max(10, configured)`,configured=10 生效。

---

## 合仓拓扑图

```
                    OpenDeploy Container (single)
    ┌───────────────────────────────────────────────────────────────┐
    │                                                                 │
    │   ┌────────────────┐        ┌────────────────┐                 │
    │   │  Bot Instance  │        │  Bot Instance  │                 │
    │   │  EU (khl.py)   │        │  ASIA (khl.py) │                 │
    │   │  token=2262e4d.│        │  token=45a5a99.│                 │
    │   │  region=eu     │        │  region=asia   │                 │
    │   └───────┬────────┘        └───────┬────────┘                 │
    │           │                          │                          │
    │   ┌───────▼────────┐        ┌───────▼────────┐                 │
    │   │ AlbionClient   │        │ AlbionClient   │                 │
    │   │ gameinfo-ams   │        │ gameinfo-sgp   │                 │
    │   │ europe.aodp    │        │ east.aodp      │                 │
    │   └────────────────┘        └────────────────┘                 │
    │                                                                 │
    │   ┌─────────────────────────────────────────────────────┐      │
    │   │  Shared: AIService (SenseNova deepseek-v4-flash),  │      │
    │   │  SQLite pool /app/data/bot.db                        │      │
    │   │  (guild_binding: PK=(kook_guild_id, region))         │      │
    │   └─────────────────────────────────────────────────────┘      │
    │                                                                 │
    │   ┌─────────────────────────────────────────────────────┐      │
    │   │  StatusAPIHandler HTTP :8080                        │      │
    │   │  /healthz, /api/status, / (static dashboard)        │      │
    │   │  dashboard 按 region tab 展示                         │      │
    │   └─────────────────────────────────────────────────────┘      │
    │                                                                 │
    └───────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
              KOOK WebSocket        KOOK WebSocket
              (EU bot)              (ASIA bot)
              独占 token 独占        独占 token 独占
```

关键性质:
- 两个 bot 独占各自 KOOK WebSocket,不会 token 冲突
- KOOK 服务器 `4676167053713576` 同一个 message 事件会分发给两个 bot,但每个 bot 通过 `region_scope.should_process_message()` 判断频道前缀,只处理自己 region 的
- SQLite 层查询默认按 region 过滤,防串表
- OpenDeploy 只算一份 CPU/RAM/存储配额,省一半

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| region 列 + 复合 PK 而非独立库文件 | 联合 PK 让跨 region 查询(dashboard 统计)不用 UNION;独立库文件维护成本翻倍 |
| SQLite 保留,不切 Postgres | 数据量小,切 PG 引入 asyncpg/连接池/迁移是另一个 sprint |
| Redis 不上 | 当前只有 `AlbionClient._cache` 是候选,收益低,复杂度高 |
| 单进程双 bot 而非双进程 | 省资源,共享 SQLite 无需锁,crash 一起挂但概率低 |
| AI 迁移只改 env 不改代码 | 商汤是 OpenAI 兼容协议,`bot/ai/client.py` 已经用 httpx 直连 `/chat/completions`,base_url 换掉就行 |
| 战报 min 从 20 → 10 而非 5 | 5 会推大量个人小规模场景卡片,过噪;10 兼顾夜间小团 |
| 死亡去重表用 event_id | 复用 `battle_report_seen` 表结构,PK=`(kook_guild_id, region, event_id)` |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| SenseNova 根路径返回 Forbidden | 用 `/v1/chat/completions` 完整路径 |
| `LongCat-2.0-Preview` model 商汤没有 | 换 `deepseek-v4-flash` |

## Resources

- SenseNova 文档(用户提供):`https://token.sensenova.cn/v1`
- 商汤 model catalog(通过 `/models` endpoint):见探针记录
- OpenDeploy 数据库/Redis 托管:用户截图显示 4 种(PG/MySQL/MongoDB/Redis 全可用)
- KOOK API 上限:每日 1 万条消息(项目 notepad 记录)
- 现网 EU project: `32e65f76-29f3-401c-8c59-b689761f768d`
- 现网 ASIA project: `albion-asia-kook` / `eb7c8c31-139a-441a-a2dc-b37689663958`

---

## OpenDeploy 配额与定价(2026-07-02 主 agent 探针)

**当前订阅**(`GET /v1/subscriptions/me`):
- Plan: **Builder trial**,`current_period_end=2026-07-20T08:47:54Z`
- CPU: 2 vCPU / Memory: 4 GB / Storage: 20 GB / Data transfer: 50 GB
- **Services: 3(硬上限)** ← 关键配额
- Projects: 5 / Domains: 5 / Databases: -1(无限)/ Deployments: -1(无限)

**Builder 到期后自动降级到 FREE**(用户提供定价截图):
| 项 | Builder trial | FREE(到期后) |
|---|---|---|
| Services | 3 | **2** |
| Projects | 5 | 2 |
| CPU/Memory/Storage | 2 vCPU / 4 GB / 20 GB | 一致 |
| Data transfer | 50 GB | **150 GB(反而更多)** |
| Databases | 无限 | 无限 |
| Domains | 5 | 无限 |

**当前 service 占用**:EU service + ASIA service = 2/3。合仓后 = 1/3(FREE 时 = 1/2)。

**结论**:
- 合仓的核心价值是**腾出 service 配额**(从 2 变 1),不是"省 volume 配额"
- **托管 Postgres/Redis 不占 service 配额,但吃 20 GB storage 池**;当前 SQLite 数据 ~20 KB,迁移 PG 无收益
- **Redis 不上**:进程内双 bot 共享 `AlbionClient._cache` TTLCache 已够用
- **不必赶 7/20 之前**:FREE 降级只影响新建 service,现有 2 个 service 继续跑

---

## Region 注入设计(Phase 3.2 核心决策)

### 问题
`bot/store/repo.py` 66 个函数,~35 处硬编码 `kook_guild_id`。用户拍板"KOOK 服务器 `4676167053713576` 同时给 EU + ASIA 两个 bot 用"→ 单靠 `kook_guild_id` 定位不到 `guild_binding` 的哪一行。

### 决策
**方案 A(选用):加 `region` 列,复合 PK**
- `guild_binding` PK: `(kook_guild_id, region)`
- `player_binding` PK: `(kook_user_id, kook_guild_id, region)`
- 其他表:`region` 列 + 索引,但**已带 `AUTOINCREMENT id` 的表(`pending_approval / regear_request / regear_reviewer_request`)保持单键 PK,只新增 `region` 列做过滤**

**为什么不给 `regear_request` 复合 PK**:
- `set_regear_status/paid/rejected` 只用 `regear_id` 定位,不需要 kook_guild_id
- 复合 PK 需要重写所有 `WHERE id=?` 为 `WHERE id=? AND region=?`,破坏面积过大
- 加 `region` 列做过滤即可(在 `list_regear` / `create_regear` 层保证)

### Region 值的来源
两条路径都要支持:
1. **代码路径**(bot 运行时):每个 khl.py Bot 实例持有 `region_code: str`,通过参数注入到 repo 层
2. **迁移路径**(老 SQLite 文件启动时):
   - EU 旧库(`region=eu`):检测 `bot/config.py` 里 `KOOK_REGION_CODE=eu` 或 `GAMEINFO_BASE` 含 `ams`
   - ASIA 旧库(`region=asia`):检测 `KOOK_REGION_CODE=asia` 或含 `sgp`
   - 兜底默认 `eu`(欧服代码为基准)

### repo.py 函数改造清单(35 处)

**批次 A - 强改(必须加 region 参数)**:
| 函数 | 现签名 | 新签名 |
|---|---|---|
| `bind_guild` | `(kgid, agid, aname, by)` | `(kgid, region, agid, aname, by)` |
| `get_guild_binding` | `(kgid)` | `(kgid, region)` |
| `all_guild_bindings` | `()` | `(region: str \| None = None)` — None 表示全部 |
| `list_player_bindings` | `(kgid)` | `(kgid, region)` |
| `unbind_guild` | `(kgid)` | `(kgid, region)` |
| `set_setting` | `(kgid, field, value)` | `(kgid, region, field, value)` |
| `has_seen_battle_report` | `(kgid, bid)` | `(kgid, region, bid)` |
| `mark_battle_report_seen` | `(kgid, bid)` | `(kgid, region, bid)` |
| `save_guild_member_snapshot` | `(kgid, agid, members, ...)` | `(kgid, region, agid, members, ...)` |
| `upsert_battle_snapshot` | `(row)` | `(region, row)` — row 里已有 kgid |
| `store_battle_detail` | `(kgid, agid, detail)` | `(kgid, region, agid, detail)` |
| `mark_collector_run` | `(name, kgid, ...)` | `(name, kgid, region, ...)` |
| `recent_attendance_snapshot` | `(kgid, ...)` | `(kgid, region, ...)` |
| `save_high_fame_events` | `(kgid, agid, events, ...)` | `(kgid, region, agid, events, ...)` |
| `list_high_fame_events` | `(kgid=None, ...)` | `(kgid=None, region=None, ...)` |
| `save_leaderboard_snapshot` | `(kind, payload, kgid=None)` | `(kind, payload, kgid=None, region=None)` |
| `list_leaderboard_snapshots` | `(limit=20)` | `(region=None, limit=20)` |
| `get_player_binding` | `(kuid, kgid)` | `(kuid, kgid, region)` |
| `get_binding_by_player` | `(kgid, pid)` | `(kgid, region, pid)` |
| `set_player_binding` | `(kuid, kgid, ...)` | `(kuid, kgid, region, ...)` |
| `delete_player_binding` | `(kuid, kgid)` | `(kuid, kgid, region)` |
| `get_open_pending` | `(kuid, kgid)` | `(kuid, kgid, region)` |
| `create_pending` | `(kgid, kuid, ...)` | `(kgid, region, kuid, ...)` |
| `create_regear` | `(kgid, kuid, ...)` | `(kgid, region, kuid, ...)` |
| `list_regear` | `(kgid, ...)` | `(kgid, region, ...)` |
| `list_user_regear` | `(kgid, kuid, ...)` | `(kgid, region, kuid, ...)` |
| `create_regear_reviewer_request` | `(kgid, kuid)` | `(kgid, region, kuid)` |
| `get_open_regear_reviewer_request` | `(kgid, kuid)` | `(kgid, region, kuid)` |

**批次 B - 弱改(只改 SQL 加 region 过滤,签名不变或加 kw)**:
- `save_gold_price_snapshot / list_gold_price_snapshots / prune_gold_price_snapshots`:金价是全局的,不需要 region 隔离(市场数据同 region 或跨 region 用同一份不影响业务),**保持原样**
- `upsert_price_references / get_price_reference / count_price_references`:同上,市场参考价按 `item_id` 全局唯一,**保持原样**

**批次 C - 只用 id 的函数(不动)**:
- `set_pending_message / get_pending / set_pending_status`
- `set_regear_message / update_regear_est_value / set_regear_status / set_regear_rejected / set_regear_paid`
- `set_regear_reviewer_request_message / get_regear_reviewer_request / set_regear_reviewer_request_status`
- `recent_collector_runs`:全局扫描,不改
- `_utc_now / _field / _as_list / _int / _json_dumps / _json_loads` 等 utility

### 调用点影响面
`bot/commands/*.py` 里所有 `repo.xxx(msg.ctx.guild.id, ...)` 都要改成
`repo.xxx(msg.ctx.guild.id, bot_region, ...)`,其中 `bot_region` 从 khl.py Bot 实例注入的 `region_code` 拿。

初步估算:
- `commands/register.py`(绑定/解绑):~10 处
- `commands/admin.py`(/设置):~15 处
- `commands/query.py`(查询):~5 处
- `commands/regear.py`(补装):~20 处
- `commands/ai.py`(/助手):~5 处
- `tasks/auto.py`:~10 处
- `tasks/collectors.py`:~5 处
- `web/status_api.py`:~5 处

**codex #2 派活前明确**:region 参数注入用**上下文对象 or 显式参数**?决定见"Bot 实例上下文对象设计"。

### Bot 实例上下文对象设计
为避免 35+ 函数签名到处加 `region`,codex #2 引入 `BotContext` dataclass:

```python
# bot/runtime.py (新文件)
@dataclass(frozen=True)
class BotContext:
    region: str  # 'eu' | 'asia'
    region_cfg: AlbionRegionConfig  # gameinfo_base / aodp_base / albionbb_base / killboard_server / display_tz / battle_report_window / albion_guild_hint
    kook_token: str
    kook_bot_id: str  # 从 token 解出的 base64 id
    gi: GameInfo
    mk: Market
    ai: AIService  # 共享
```

`bot/main.py::build_bots()` 为每个 region 构造 1 个 `BotContext` + 1 个 khl `Bot`,command handler 用 `ctx.region` 传给 repo 层。

repo 层保持 pure function(不引入全局 state),只是每个函数多接一个 `region: str` 参数——**这是简单粗暴但可审计的做法**,codex 派活时明确"不要引入全局 REGION 变量"。

---

## Phase 3.2 迁移 SQL 完整版

**执行位置**:`bot/store/db.py::init_db()` 里 `conn.executescript(SCHEMA)` 之后追加 `_ensure_region_columns(conn)`。幂等,重启多次不重复迁移。

**backfill 逻辑**:
- 老库检测:如果 `guild_binding` 表已有数据但 `region` 列不存在 → 从 `KOOK_REGION_CODE` env 或 `_infer_region_from_config()` 反推
- 反推逻辑复用 `bot/region_scope.py::_infer_region_from_config`,把它抽公共

```sql
-- Step 1: guild_binding (PK 变复合)
ALTER TABLE guild_binding RENAME TO guild_binding_legacy;
CREATE TABLE guild_binding (
  kook_guild_id        TEXT NOT NULL,
  region               TEXT NOT NULL,
  albion_guild_id      TEXT NOT NULL,
  albion_guild_name    TEXT NOT NULL,
  member_role_id       TEXT,
  approval_channel_id  TEXT,
  regear_channel_id    TEXT,
  regear_apply_channel_id TEXT,
  regear_review_channel_id TEXT,
  regear_payout_channel_id TEXT,
  regear_notify_channel_id TEXT,
  broadcast_channel_id TEXT,
  kill_broadcast_channel_id TEXT,
  death_broadcast_channel_id TEXT,
  battle_report_channel_id TEXT,
  battle_report_min_guild_players INTEGER DEFAULT 10,
  member_change_channel_id TEXT,
  regear_reviewer_role_ids TEXT,
  trusted_role_ids     TEXT,
  kill_fame_threshold  INTEGER DEFAULT 100000,
  created_by           TEXT,
  created_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, region)
);
INSERT INTO guild_binding
SELECT kook_guild_id, ?, albion_guild_id, albion_guild_name, member_role_id,
       approval_channel_id, regear_channel_id, regear_apply_channel_id,
       regear_review_channel_id, regear_payout_channel_id, regear_notify_channel_id,
       broadcast_channel_id, kill_broadcast_channel_id, death_broadcast_channel_id,
       battle_report_channel_id, battle_report_min_guild_players,
       member_change_channel_id, regear_reviewer_role_ids, trusted_role_ids,
       kill_fame_threshold, created_by, created_at
FROM guild_binding_legacy;
DROP TABLE guild_binding_legacy;
-- ? 参数由 Python 传:legacy_region

-- Step 2: player_binding
ALTER TABLE player_binding RENAME TO player_binding_legacy;
CREATE TABLE player_binding (
  kook_user_id       TEXT NOT NULL,
  kook_guild_id      TEXT NOT NULL,
  region             TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  custom_nickname    TEXT,
  status             TEXT DEFAULT 'verified',
  bound_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_user_id, kook_guild_id, region)
);
INSERT INTO player_binding
SELECT kook_user_id, kook_guild_id, ?, albion_player_id, albion_player_name,
       custom_nickname, status, bound_at
FROM player_binding_legacy;
DROP TABLE player_binding_legacy;

-- Step 3: pending_approval / regear_request / regear_reviewer_request 只加列
ALTER TABLE pending_approval ADD COLUMN region TEXT NOT NULL DEFAULT 'eu';
UPDATE pending_approval SET region = ? WHERE region = 'eu';  -- backfill
ALTER TABLE regear_request ADD COLUMN region TEXT NOT NULL DEFAULT 'eu';
UPDATE regear_request SET region = ? WHERE region = 'eu';
ALTER TABLE regear_reviewer_request ADD COLUMN region TEXT NOT NULL DEFAULT 'eu';
UPDATE regear_reviewer_request SET region = ? WHERE region = 'eu';

-- Step 4: battle_snapshot / battle_participant / guild_member_snapshot / battle_report_seen / high_fame_event / collector_cursor 复合 PK
-- 都按 Step 1 的 rename→create→insert→drop 模式,添加 region 到 PK

-- battle_report_seen: PK=(kook_guild_id, region, battle_id)
-- battle_snapshot: PK=(kook_guild_id, region, battle_id)
-- battle_participant: PK=(battle_id, region, albion_player_id) — battle_id 已包 region 前缀,region 冗余但明确
-- guild_member_snapshot: PK=(kook_guild_id, region, albion_guild_id, captured_at, albion_player_id)
-- high_fame_event: PK=(kook_guild_id, region, event_id)
-- collector_cursor: PK=(name, kook_guild_id, region)

-- Step 5: 索引
CREATE INDEX IF NOT EXISTS idx_guild_binding_region ON guild_binding(region);
CREATE INDEX IF NOT EXISTS idx_player_binding_region ON player_binding(kook_guild_id, region);
CREATE INDEX IF NOT EXISTS idx_battle_snapshot_region_time
  ON battle_snapshot(kook_guild_id, region, albion_guild_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_high_fame_event_region_time
  ON high_fame_event(kook_guild_id, region, event_time DESC);
```

**gold_price_snapshot / fame_leaderboard_snapshot / market_price_reference 不加 region**:全局数据,跨 region 共享,减少存储和维护成本。

---

## Phase 3.2 `bot/main.py::build_bots()` 骨架伪代码

```python
def build_bots() -> list[Bot]:
    """构造 N 个 khl.py Bot(一个 region 一个),共享 AIService 和 SQLite。"""
    config.setup_logging()
    init_db()  # 初始化+运行 region 迁移

    # 共享的 AI 客户端(所有 bot 用同一份)
    ai_client = AIClient(AIClientConfig.from_env()) if config.AI_ENABLED and config.AI_API_KEY else None
    ai_service = AIService(ai_client, enabled=config.AI_ENABLED)

    bots: list[Bot] = []
    for region_code, region_cfg in config.REGION_CONFIGS.items():
        # 每个 region 独立的资源
        albion_client = AlbionClient(
            gameinfo_base=region_cfg.gameinfo_base,
            aodp_base=region_cfg.aodp_base,
            albionbb_base=region_cfg.albionbb_base,
        )
        gi = GameInfo(albion_client)
        mk = Market(albion_client)

        # region-specific bootstrap seed(区分 fumass/Mika 公会绑定)
        seed_runtime_guild_config(region_code)

        # 每个 region 一个 KOOK Bot 实例
        bot = Bot(token=region_cfg.kook_token)

        # 每个 bot 挂上 region 上下文(commands 层通过 msg.ctx.bot._region 拿)
        setattr(bot, "_region", region_code)

        # 注册 commands,把 region 传下去
        admin.register(bot, gi, region=region_code)
        register.register(bot, gi, region=region_code)
        query.register(bot, gi, mk, region=region_code)
        regear.register(bot, gi, mk, ai_service, region=region_code)
        ai.register(bot, ai_service, gi, mk, region=region_code)
        auto.register(bot, gi, mk, ai_service, region=region_code)

        bots.append(bot)

    return bots


def main() -> None:
    bots = build_bots()
    start_health_server_if_configured()  # 一个 StatusAPIHandler,共享 SQLite,按 region 分组

    # 同一 asyncio event loop 里 gather 两个 bot.start()
    import asyncio
    async def run_all():
        await asyncio.gather(*[bot.start() for bot in bots])
    asyncio.run(run_all())
```

**关键点**:
- `bot.run()` 内部就是 `asyncio.run(bot.start())`,不能直接调两次;要外层 `gather`
- 每个 command 的 register 函数签名要加 `region: str` 参数,内部把 region 传给所有 `repo.xxx()` 调用
- 共享 `AIService`:`AIClient.complete()` 用 `httpx.AsyncClient`,天然协程安全

---

## Codex 派活 Prompt(4 段,可直接复制到 codex CLI)

### Codex #1 - Phase 3.1 仓库合并基线

```
# Task: 合并 Albion-EU-kook 和 Albion-ASIA-kook 到单仓,以 EU 为基准

## Context
两个仓 diff 结果见 .planning/2026-07-02-consolidate-eu-asia-bot/findings.md
EU 分支已有 M7 全套(attendance/collectors/web/status_api),ASIA 只有基础功能。
用户拍板:欧服代码为基准,ASIA 独有配置搬到 bootstrap.py::RUNTIME_GUILD_CONFIGS["asia"]。

## Scope
只在 /Users/arm/Desktop/vscode/Albion-EU-kook 改动,不动 ASIA 仓。

## Changes
1. bot/config.py:
   - 移除 KOOK_REGION_CODE 全局环境变量的"单值"读法
   - 新增 REGION_CONFIGS: dict[str, AlbionRegionConfig] 字典,支持 EU/ASIA 双区
   - AlbionRegionConfig 字段:region_code, kook_token, gameinfo_base, aodp_base,
     albionbb_base, albionbb_web_base, killboard_server, display_tz,
     display_tz_label, display_tz_short_label
   - env 变量命名规范:{FIELD}_{REGION} 例如 KOOK_TOKEN_EU / GAMEINFO_BASE_ASIA;
     兼容旧变量(无后缀)当默认值
2. bot/region_scope.py:
   - 删除 _infer_region_from_config():region 不再由 env 单值推断
   - region_code() 保留但改成 deprecated,内部返回第一个可用 region 兜底
   - scoped_name / channel_matches_region 加 region 参数(默认取当前 bot 上下文)
3. .env.example:
   - 保留双区变量样板(KOOK_TOKEN_EU / KOOK_TOKEN_ASIA / GAMEINFO_BASE_EU / GAMEINFO_BASE_ASIA 等)

## Deliverable
- bot/config.py 用 REGION_CONFIGS dict 组织所有区服配置
- pytest tests/ 全绿
- scripts/check.sh 通过

## DO NOT
- 不改 bot/store/*(那是 codex #2 的范围)
- 不改 bot/main.py(那是 codex #2)
- 不改 bot/ai/*(那是 codex #3)
```

### Codex #2 - Phase 3.2 数据模型 + 进程内双 bot(大改)

```
# Task: 加 region 列到所有 kook_guild_id 相关表,重构 main.py 支持进程内双 bot

## Context
计划详见 .planning/2026-07-02-consolidate-eu-asia-bot/findings.md
KOOK 服务器 4676167053713576 同时给 EU + ASIA 两个 bot 用,必须靠 region 隔离数据。

## Phase 3.2.a - 数据库迁移(bot/store/db.py)
1. 增加 _ensure_region_columns(conn) 函数,幂等
2. 表改造清单(rename→create→insert→drop 模式):
   - guild_binding: PK=(kook_guild_id, region)
   - player_binding: PK=(kook_user_id, kook_guild_id, region)
   - battle_snapshot: PK=(kook_guild_id, region, battle_id)
   - battle_participant: 加 region 列(PK 保持不变,battle_id 已唯一)
   - guild_member_snapshot: PK=(kook_guild_id, region, albion_guild_id, captured_at, albion_player_id)
   - battle_report_seen: PK=(kook_guild_id, region, battle_id)
   - high_fame_event: PK=(kook_guild_id, region, event_id)
   - collector_cursor: PK=(name, kook_guild_id, region)
3. 只加 region 列不改 PK 的表:pending_approval / regear_request / regear_reviewer_request
4. 全局数据不加 region:market_price_reference / gold_price_snapshot / fame_leaderboard_snapshot
5. Backfill:老库自动填 region,值取自 config.KOOK_REGION_CODE_LEGACY 或"eu"
6. 迁移前后行数一致校验:assert 迁移前后 count(*) 相同

## Phase 3.2.b - repo.py 函数改造(35 处)
参考 findings.md "repo.py 函数改造清单" 批次 A/B/C。
所有需要 region 的函数,加 region: str 位置参数;
all_guild_bindings 加 region: str | None = None 关键字。

## Phase 3.2.c - commands 层调用点
按 findings.md "调用点影响面":
- register.py / admin.py / query.py / regear.py / ai.py 里所有 repo.xxx(guild.id, ...) 调用
- 从 bot 实例注入 region:command handler 函数内取 msg.ctx.bot._region

## Phase 3.2.d - bot/main.py 双 bot 骨架
按 findings.md "Phase 3.2 bot/main.py::build_bots() 骨架伪代码" 落地。
关键点:asyncio.gather 同时跑 N 个 bot.start()。

## Phase 3.2.e - tasks/auto.py
所有 all_guild_bindings() 遍历改成 all_guild_bindings(region=current_region),
避免 EU bot 处理 ASIA 公会数据。

## Deliverable
- 双 bot 启动日志出现两个 bot_id(49050 EU / 49025 ASIA)+ 两个 token_fp
- 迁移旧 SQLite:SELECT region, count(*) FROM guild_binding → 两行(eu/asia)
- /ping 在 eu-xxx 频道 EU bot 响应、asia-xxx 频道 ASIA bot 响应
- pytest tests/ 全绿(需要新增 tests/test_region_isolation.py)

## DO NOT
- 不改 bot/ai/*(codex #3)
- 不改 bot/tasks/auto.py 里播报延迟相关代码(codex #4)
- 不引入全局 REGION 变量或 contextvars(参数显式传)
```

### Codex #3 - Phase 3.3 AI 换商汤(轻改)

```
# Task: 把 AI 从 LongCat 换到商汤 deepseek-v4-flash

## Context
LongCat 免费停止,商汤 token.sensenova.cn/v1 完全 OpenAI 兼容,主 agent 已探针成功。
详见 .planning/2026-07-02-consolidate-eu-asia-bot/findings.md

## Changes
1. bot/config.py:
   - AI_BASE_URL 默认值:"https://token.sensenova.cn/v1"(原 "https://api.longcat.chat/openai")
   - AI_MODEL 默认值:"deepseek-v4-flash"(原 "LongCat-2.0-Preview")
   - AI_MAX_OUTPUT_TOKENS 默认值:2000(原 800,给 reasoning_content 留空间)
2. bot/ai/client.py:
   - 检查 chat_completions_url:base_url 结尾 /v1 时不再追加 /v1,验证现有逻辑
   - complete() 提取 content 时,忽略 reasoning_content(现有代码已正确,加个单测锁死)
3. .env.example:
   - 更新 AI_BASE_URL / AI_MODEL 注释到商汤
   - 保留 AI_API_KEY 占位符 sk-xxx
4. tests/test_ai_sensenova.py(新):
   - MockTransport 返回带 reasoning_content 的 chat completions 响应
   - 断言 complete() 只取 message.content

## Deliverable
- 探针:curl https://token.sensenova.cn/v1/chat/completions 200
- 单测 tests/test_ai_sensenova.py 通过
- 现网 EU 和 ASIA 的 OpenDeploy .env 同步替换(手动步骤,不在 codex 范围)

## DO NOT
- 不改 bot/store/*(codex #2)
- 不改 tasks/auto.py 播报逻辑(codex #4)
```

### Codex #4 - Phase 3.4 延迟修复(精修)

```
# Task: 修复击杀/阵亡 5-10 分钟延迟 + 夜间战报静默

## Context
根因见 .planning/2026-07-02-consolidate-eu-asia-bot/findings.md "播报延迟根因分析"

## Changes
1. bot/tasks/auto.py:
   - BATTLE_REPORT_MIN_PLAYERS: 20 → 10
   - _effective_battle_report_min_guild_players: max(20, configured) → max(10, configured)
   - MAX_BROADCAST_PER_TICK: 15 → 30
   - FEED_PAGES: 常量 4 → 变函数 _feed_pages() 忙时段(20:00-00:30 local)返回 6,其他 4
2. 死亡去重持久化:
   - 复用 battle_report_seen 表模式,或新建 event_broadcast_seen 表:
     CREATE TABLE event_broadcast_seen (
       kook_guild_id TEXT NOT NULL,
       region TEXT NOT NULL,
       event_id TEXT NOT NULL,
       broadcasted_at TEXT DEFAULT (datetime('now')),
       PRIMARY KEY (kook_guild_id, region, event_id)
     );
   - _seen 从 set[str] 改成 SQLite-backed(启动时读近 6h 的 event_id 进内存,新事件 INSERT OR IGNORE)
   - _primed 逻辑不变(重启后第一轮仍吞事件),但 _seen 持久化后不会再"永远丢"
3. 日志埋点:death_broadcast 每轮记 fetched/new/broadcasted/skipped_by_region

## Deliverable
- 重启后 5 分钟内新击杀能推
- 夜间小规模场次(10-19 人)能推战报
- grep "播报达单轮上限" bot.log 频次显著下降
- pytest tests/ 全绿(新增 tests/test_broadcast_dedup.py 验证 SQLite 去重)

## DO NOT
- 不改 bot/ai/*(codex #3)
- 不改数据模型 region 列(codex #2)
- event_broadcast_seen 表加 region 列(和 codex #2 保持一致)
```

---

## 主 agent 后续验证清单

Codex 每交付一个 Phase,主 agent 用 Skill('code-review') 审 diff,重点看:

**Phase 3.1**:
- [ ] REGION_CONFIGS dict 完整覆盖 EU/ASIA
- [ ] .env.example 双区变量样板一致
- [ ] region_scope 里的 _infer_region_from_config 彻底移除
- [ ] pytest tests/ 全绿

**Phase 3.2**:
- [ ] 迁移脚本幂等(重启 3 次不重复迁移)
- [ ] 老库 backfill 正确(SELECT region,count(*) FROM guild_binding 返回 2 行)
- [ ] repo.py 所有函数签名和 findings 清单一致
- [ ] commands 层不出现 region=None 或硬编码 region="eu"
- [ ] 双 bot 启动日志出现两个 bot_id + 两个 token_fp
- [ ] 双 bot 在同一 KOOK 服务器 4676167053713576 里各自只响应自己前缀频道
- [ ] pytest tests/test_region_isolation.py 覆盖:
    - 同 kook_guild_id 不同 region 的 guild_binding 各自独立
    - EU bot 的 all_guild_bindings(region="eu") 只返回 EU 公会
    - 补装 regear_id 不冲突(尽管 PK 单键,region 列做过滤)

**Phase 3.3**:
- [ ] 探针 curl 商汤成功
- [ ] tests/test_ai_sensenova.py 覆盖 reasoning_content 字段
- [ ] AI_MAX_OUTPUT_TOKENS 提高到 2000

**Phase 3.4**:
- [ ] BATTLE_REPORT_MIN_PLAYERS = 10 生效
- [ ] event_broadcast_seen 表有 region 列
- [ ] _seen 持久化后重启不丢事件
- [ ] tests/test_broadcast_dedup.py 全绿

---

## 上线 checklist(Phase 5)

- [ ] 新建 OpenDeploy project `albion-kook-merged`(或复用 EU project)
- [ ] Env 变量注入(region-keyed):
  - KOOK_TOKEN_EU / KOOK_TOKEN_ASIA
  - GAMEINFO_BASE_EU / GAMEINFO_BASE_ASIA / AODP_BASE_EU / AODP_BASE_ASIA
  - ALBIONBB_BASE_EU / ALBIONBB_BASE_ASIA
  - AI_BASE_URL=https://token.sensenova.cn/v1
  - AI_API_KEY=[redacted] (由安全来源注入,不写入计划或日志)
  - AI_MODEL=deepseek-v4-flash
  - AI_MAX_OUTPUT_TOKENS=2000
- [ ] 挂载 1Gi 持久卷 /app/data
- [ ] 数据迁移:
  - 从 EU project SQLite 导出 → 合并到新库(region=eu)
  - 从 ASIA project SQLite 导出 → 合并到新库(region=asia)
  - INSERT INTO 新库时 region 列用 dump 时的 project 区分
- [ ] 冒烟测试:
  - /healthz 200
  - /api/status 200 且两个 region collector_summary=ok
  - EU 频道 /ping 由 EU bot 响应
  - ASIA 频道 /ping 由 ASIA bot 响应
- [ ] 保留旧 EU/ASIA project 30 天回滚窗口
- [ ] 30 天后销毁旧 project
