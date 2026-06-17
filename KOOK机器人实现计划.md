# 阿尔比恩公会 KOOK 机器人 — 实现计划

> 配套文档：`阿尔比恩数据接口文档.md`（数据源、端点、字段、估值逻辑都在那）
> 本计划假设：旧的 React 前端 + Node backend 已归档不再维护 → 新项目走**单一 Python 自包含**，不依赖旧 backend。
> 当前项目版本：`1.0`，代码单一来源为 `bot/version.py`。

---

## 一、目标与范围

做一个面向**单个阿尔比恩公会**的 KOOK 频道机器人，核心两条主线：

1. **管理员绑公会** —— 频道管理员及以上权限，把本 KOOK 服务器绑定到一个 Albion 公会。
2. **玩家自助绑角色** —— 公会成员在频道内自助绑定游戏角色，走「名字匹配 + 管理员审批」（方案二），通过后获得会员身份组。

绑定建立后，玩家用查询指令免再输名字。

**本期不做**：语音交互、跨多公会、历史趋势/胜率矩阵（要长期落库，后续再说）。

---

## 二、技术选型

| 项 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.11+ | KOOK SDK 成熟度最高 |
| KOOK SDK | **khl.py** | 封装好 WebSocket 心跳/重连、指令、卡片、按钮事件 |
| 连接模式 | **WebSocket** | 机器人主动外连，**无需公网域名、无需 ICP 备案、不限服务器位置**（本地/海外 VPS 均可） |
| HTTP 客户端 | httpx | 异步，配合 khl.py |
| 存储 | SQLite | 绑定关系数据量小，零运维 |
| 版本号 | `bot/version.py` | 单一版本来源，`/ping` 返回当前版本 |
| 鉴权 | KOOK Bot Token（env 注入，不入库不进 git） | — |

> KOOK 没有原生斜杠指令注册，靠监听 `message` 事件解析 `/` 前缀（khl.py 的 `@bot.command` 已封装）。交互按钮用卡片 `click=return-val`，点击回推 button-click 事件，无需额外回调地址。

---

## 三、架构

```
KOOK ←─WebSocket─→ [机器人进程 (Python/khl.py)]
                        │
                        ├─ albion/ 数据层 ──HTTP──→ gameinfo-sgp / AODP(east) / albionbb(asia)
                        │     (自带缓存 + 限流 + 退避)
                        │
                        └─ store/ SQLite ── 绑定关系 + 审批状态
```

机器人只需要 ~5 个只读端点，自带轻量缓存/退避即可，不重建旧 backend 的全部能力。

---

## 四、数据层（按接口文档实现）

只实现机器人用得到的调用：

| 模块 | 端点 | 用途 |
|---|---|---|
| `gameinfo.search(q)` | `/search?q=` | 公会名/角色名 → 拿 base64 ID |
| `gameinfo.player(id)` | `/players/{id}` (+`/kills` `/deaths`) | 玩家档案、终身声望、最近死亡 |
| `gameinfo.guild(id)` | `/guilds/{id}` (+`/members`) | 公会信息、成员（退会复查用） |
| `gameinfo.events(guild_id=None)` | `/events`、`/events?guildId=` | 死亡播报。实测 guild feed 只含本会击杀，阵亡播报走全局 `/events` 多页 + 双向筛 |
| `gameinfo.player_fame()` / `player_statistics()` | `/events/playerfame`、`/players/statistics` | 声望榜（PvP/PvE） |
| `gameinfo.battles(guildId)` / `battle()` / `battle_events()` | `/battles?guildId=`、`/battles/{id}`、`/events/battle/{id}` | 战役查询、战报聚合、后续出勤统计 |
| `market.prices(types, q)` | AODP `/api/v2/stats/prices/{items}.json` | 物价即时查询（`/物价`） |
| `market.history(types)` | AODP `/api/v2/stats/history/{items}.json?time-scale=24` | 估值口径：近 N 天各城 avg_price |
| `market.gold()` | AODP `/api/v2/stats/gold.json` | 金价 |

要点（来自接口文档实测）：
- 区服一致：战斗 `gameinfo-sgp`、市场 `east.albion-online-data.com`、ZvZ `api.albionbb.com/asia`。
- KOOK 频道作用域一致：亚服实例使用 `KOOK_REGION_CODE=asia`，只响应和发送到 `asia-` 前缀频道；无前缀或其他区服前缀频道静默。
- 先 `/search` 拿 ID 再查详情。
- AODP 限流 **180/分**，批量逗号查 + 本地缓存价格。
- 亚服挂单稀疏 + 离群噪音 → 估值取多城中位/最低正价，或用 `/history` 近 N 天均价兜底。
- 不可交易物（技能书等）查不到价 → 跳过记 0。
- 官方 API 偶发故障 → 全部调用要容错 + 退避。

估值逻辑直接搬接口文档第七节（10 槽 Equipment + Inventory 数组 → AODP 累加）。

---

## 五、验证流程（方案二：名字匹配 + 管理员审批）

```
玩家 /绑定 <角色名> [自定义昵称]
   │
   ├─ search + players/{id} 查角色
   │     ├─ 角色不存在 → 直接拒，提示
   │     └─ 角色.GuildId != 本服已绑公会 → 直接拒，提示"该角色不在本公会"
   │
   └─ 命中 → KOOK 角色预检（信心分级，非硬门槛）
              ├─ 已持「可信身份组」(管理员配置) → 快速通道，可自动通过
              └─ 无可信身份组 → 「审批频道」发待审批卡片(含角色名/IP/公会/目标昵称)
                                  管理员点 [通过] / [拒绝] 按钮
                 通过 → 发会员身份组 + 改 KOOK 昵称为角色名或"角色名 - 自定义昵称" + 落库 player_binding
                 拒绝 → 标记 rejected，通知玩家
```

> 所有权验证的局限已知：API 无密码/简介字段，纯名字可冒填。两道把关叠加降冒名残余风险：
> - **API 校验**证「这个角色在公会」（`GuildId` 命中）。
> - **KOOK 角色预检**证「这个 KOOK 用户被公会信任」（公会少给非成员权限）。
> 注意：预检只做信心分级、不做硬门槛——新人此刻没有任何身份组，硬卡会死锁绑定流程。无可信身份组者照旧走管理员人眼把关。

---

## 六、存储 schema（SQLite）

```sql
-- 公会绑定（一个 KOOK 服务器绑一个公会）
guild_binding(
  kook_guild_id              TEXT PRIMARY KEY,
  albion_guild_id            TEXT NOT NULL,
  albion_guild_name          TEXT NOT NULL,
  member_role_id             TEXT,
  approval_channel_id        TEXT,
  regear_channel_id          TEXT, -- 旧单频道兼容兜底
  regear_apply_channel_id    TEXT,
  regear_review_channel_id   TEXT,
  regear_payout_channel_id   TEXT,
  regear_notify_channel_id   TEXT,
  broadcast_channel_id       TEXT,
  kill_broadcast_channel_id  TEXT,
  death_broadcast_channel_id TEXT,
  battle_report_channel_id   TEXT,
  member_change_channel_id   TEXT,
  regear_reviewer_role_ids   TEXT, -- 逗号分隔，补装审核/发放身份组
  trusted_role_ids           TEXT, -- 逗号分隔，绑定快速通道身份组
  kill_fame_threshold        INTEGER DEFAULT 100000, -- legacy：旧大额阈值兼容字段，运行时不再读取
  created_by                 TEXT,
  created_at                 TEXT DEFAULT (datetime('now'))
)

player_binding(
  kook_user_id       TEXT NOT NULL,
  kook_guild_id      TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  custom_nickname    TEXT,
  status             TEXT DEFAULT 'verified',
  bound_at           TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_user_id, kook_guild_id)
)

pending_approval(
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id      TEXT NOT NULL,
  kook_user_id       TEXT NOT NULL,
  albion_player_id   TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  custom_nickname    TEXT,
  message_id         TEXT,
  status             TEXT DEFAULT 'pending',
  created_at         TEXT DEFAULT (datetime('now'))
)

regear_request(
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id    TEXT NOT NULL,
  kook_user_id     TEXT NOT NULL,
  albion_player_id TEXT,
  event_id         TEXT,
  est_value        INTEGER,
  message_id       TEXT,
  status           TEXT DEFAULT 'pending', -- pending/approved/rejected/paid
  created_at       TEXT DEFAULT (datetime('now')),
  reviewed_by      TEXT,
  reviewed_at      TEXT,
  paid_by          TEXT,
  paid_at          TEXT
)

regear_reviewer_request(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kook_guild_id TEXT NOT NULL,
  kook_user_id  TEXT NOT NULL,
  message_id    TEXT,
  status        TEXT DEFAULT 'pending',
  created_at    TEXT DEFAULT (datetime('now')),
  reviewed_by   TEXT,
  reviewed_at   TEXT
)

market_price_reference(
  item_id      TEXT NOT NULL,
  quality      INTEGER NOT NULL,
  slot_group   TEXT NOT NULL,
  low_price    INTEGER NOT NULL,
  sample_count INTEGER DEFAULT 0,
  source       TEXT DEFAULT 'aodp_prices_sell_min',
  updated_at   TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (item_id, quality)
)
```

---

## 七、指令清单

**管理员**（发起人身份组需 ≥ 频道管理员，用 KOOK 角色权限位校验）
- `/绑定公会 <公会名>` → search 列候选 → 按钮选中 → 落库
- `/设置 会员身份组 @身份组`
- `/设置 审批频道 #频道`
- `/设置 运营初始化频道` → 新建或复用 `asia-📡运营中心`，并写入审批、成员变动、击杀、阵亡、战报频道配置
- `/设置 补装初始化频道` → 新建或复用 `asia-🛡️补装中心` 四频道并写入配置
- `/设置 补装申请频道|补装审核频道|补装发放频道|补装通知频道 #频道`
- `/设置 补装频道 #频道` → 旧单频道兼容兜底
- `/设置 补装审核身份组 @身份组[ @身份组...]`
- `/设置 播报频道 #频道` → 统一播报兜底
- `/设置 击杀播报频道 #频道`
- `/设置 阵亡播报频道 #频道`（兼容 `/设置 死亡播报频道 #频道`）
- `/设置 战报推送频道 #频道`（兼容 `/设置 战报频道 #频道`）
- `/设置 战报本会最小人数 <人数>` → 自动战报推送阈值，默认 20 人，低于 20 按 20 生效
- `/设置 成员变动频道 #频道`
- `/设置 大额阈值 <fame>`  → 旧命令兼容提示；大额规则固定，不再改变运行时阈值
- `/解绑公会`

**玩家**
- `/绑定 <角色名> [自定义昵称]` → 走第五节审批流；自定义昵称会同步为 `角色名 - 自定义昵称`
- `/解绑`
- `/补装` → 选最近死亡 → 看详情或提交补装申请
- `/补装状态` → 查看本人最近补装进度
- `/补装审核` → 申请补装审核身份组

**查询**（已绑定用户免输名字）
- `/战绩 [角色名]` → 玩家档案 + KD + 最近击杀/死亡
- `/估值` → 最近一次死亡的装备+背包估值（AODP）
- `/战役` → 公会最近 ZvZ 战役（官方 `/battles?guildId=`）
- `/物价 <物品>` → AODP 现价
- `/金价` → AODP `gold.json`，近 24h 价格与波动
- `/榜单 [pvp|pve]` → 声望榜：PvP `/events/playerfame`、PvE `/players/statistics?type=PvE`
- `/战报 [日期]` → AI 基于最近战役生成短摘要；带日期时按北京时间目标日 14:30 到次日 05:00 过滤
- `/助手 <问题>` → 命令引导 + 白名单只读查询
- `/补装解释 <申请号>` → AI 解释补装金额和异常点，不参与审批
- `/补装 待处理|待发放|列表` → 管理员或补装审核员查看队列
- `/出勤` → 最近 N 场 `/battles?guildId=` 聚合参战者，出成员出勤快照（趋势版需采集器，归二期）

**自动（一期，与查询同期落地）**
- 死亡播报：定时轮询全局 `/events` 多页，按 killer/victim 双向筛出本会击杀/阵亡，分别推到当前区服前缀的对应播报频道，未单独配置则推到当前区服前缀的统一播报兜底频道
  - 区分**我方击杀 / 我方阵亡**；击杀/死亡声望大于 100 万，或银币总损失大于 1000 万时**大额高亮**推送
  - 注意 KOOK 每日发消息上限 1 万，控频 + 去重
- 退会复查：每日比对 `/guilds/{id}/members` → 退会自动撤销身份组，并通知当前区服前缀的成员变动频道
- 价格参考库刷新：每 3 天刷新 T4-T8 主手/双手/副手低价参考
- 战报自动推送：北京时间 14:30 到次日 05:00 每 15 分钟检查 AlbionBB 候选战役，按绑定公会、至少 20 名本会参战者和持久去重表过滤后推送到当前区服前缀的专属战报频道；当前尚未 KOOK/线上活测

---

## 八、项目结构

```
albion-kook-bot/
├── bot/
│   ├── main.py              # khl.py Bot 启动 + WS 连接
│   ├── config.py            # env: KOOK_TOKEN 等
│   ├── version.py           # 项目版本号，当前 1.0
│   ├── ai/                  # LongCat/OpenAI 兼容 AI 辅助，只读路由和安全输出层
│   ├── commands/
│   │   ├── admin.py         # 绑定公会 / 设置
│   │   ├── ai.py            # /助手 /战报 /补装解释
│   │   ├── register.py      # 玩家绑定 + 审批（含 KOOK 角色预检分级）
│   │   ├── query.py         # 战绩 / 估值 / 战役 / 物价 / 金价 / 榜单
│   │   └── regear.py        # 补装申请 + 审批记账
│   ├── cards/               # 卡片构建（选公会、审批、战绩、估值、补装、播报、战报）
│   ├── tasks/               # 定时轮询：死亡播报 + 退会复查（共用调度骨架）
│   ├── albion/
│   │   ├── client.py        # httpx + 缓存 + 限流 + 退避
│   │   ├── gameinfo.py      # search/players/guilds/events/battles/fame
│   │   ├── market.py        # AODP prices + gold
│   │   ├── battle_report.py # ZvZ 战报聚合
│   │   ├── valuation.py     # 装备+背包估值
│   │   └── items.py         # ao-bin-dumps 物品名→中文
│   └── store/db.py          # SQLite
├── data/bot.db
├── 阿尔比恩数据接口文档.md     # 从旧项目迁移进来
├── requirements.txt
├── .env.example             # KOOK_TOKEN=
└── README.md
```

---

## 九、里程碑（每步带验证标准）

| 阶段 | 内容 | 验证 |
|---|---|---|
| **M0 脚手架** | khl.py 连上 KOOK WS，`/ping` 回 `pong v1.0` | 频道发 `/ping` 收到带版本回复 |
| **M1 数据层** | `albion/client+gameinfo+market+valuation` | 对真实角色名跑通：返回档案、估值为非负数 |
| **M2 公会绑定** | `/绑定公会` 权限校验 + search + 按钮选中 + 落库 | 非管理员被拒；管理员绑成功且 DB 有记录 |
| **M3 玩家绑定+审批** | `/绑定` → 审批卡片 → 按钮通过 → 发组+改名 | 不在公会的角色被拒；在公会的走审批后拿到身份组 |
| **M4 查询指令** | `/战绩 /估值 /战役 /物价 /金价 /榜单` | 已绑定用户免输名字直接出结果 |
| **M5 补装** | `/补装` → 选死亡 → 复用估值 → 申请卡片 → 批准记账 | 申请走审批后 regear_request 落 approved |
| **M6 自动任务** | 死亡播报（分击杀/阵亡+大额高亮）+ 退会复查 | 公会有死亡时频道收到卡片；大额单独高亮；退会成员身份组被撤 |
| **AI 辅助** | `/助手`、`/战报`、`/补装解释`，只读事实包 + 输出安全层 | LongCat 探针通过；只读边界和危险声明拦截有单测 |
| **版本号控制** | `bot/version.py` 统一版本，`/ping` 带版本 | `tests/test_version.py` 通过 |
| **战报聚合/自动推送** | 生成 ZvZ 聚合报告和 KOOK 卡片，按专属频道自动推送并持久去重 | 已完成离线测试、KOOK 专属频道发送验证和线上服务验证 |
| **M7 出勤（快照）** | `/出勤` 最近 N 场参战者聚合 | 出成员出勤次数快照（趋势版+采集器归二期） |

---

## 十、风险与注意

1. **所有权验证非强保证** —— 方案二靠管理员人眼，接受冒名残余风险；后续要更强可加"改名挑战"。
2. **官方 API 偶发故障**（社区常态）—— 所有调用容错 + 退避，失败给友好提示而非崩。
3. **亚服市场稀疏 + 离群噪音** —— 估值做兜底（多城中位/历史均价），不取单点。
4. **KOOK 每日发消息上限 1 万** —— 死亡播报要控频 + 去重，避免刷爆配额。
5. **Token 安全** —— 走 env，不入库不进 git；`.env` 加 `.gitignore`。
6. **区服别混** —— 战斗 sgp / 市场 east / ZvZ asia / KOOK `asia-` 频道前缀都得是亚服。
7. **AI 边界** —— AI 只做说明和只读查询，不允许批准绑定、批准补装、改金额、发组、撤组或标记发放。

---

## 十一、决议 / 下一步

已收口（2026-06-14）：
- **死亡播报 + 退会复查** → 一期一起做（共用定时轮询骨架，见第七节、M5）。
- **估值默认口径** → 红城（Caerleon）卖单最低正价，过滤 0/离群；缺数据回退多城中位或 `/history` 近 N 天 `avg_price`。同类 bot（bridgewatcher 等）默认即红城/黑市价。展示标注「按红城均价估算」。
- **所有权验证** → 加 KOOK 角色预检做信心分级（已持可信身份组+API 命中可快速通过），非硬门槛，见第五节。

- **功能盘缺口**（对比同类 bot 收口）→ 一期补：`/金价`、`/榜单`、死亡播报分击杀/阵亡+大额高亮、`/补装`（复用估值+审批）；`/出勤`一期只做最近 N 场快照，趋势版+采集器归二期。明确不做：经济/虚拟银行/税、CTA 排期、运输套利、武器对战矩阵。
- **物品中文名** → 一期接 ao-bin-dumps（唯一权威源，`LocalizedNames["ZH-CN"]`），预处理成本地 dict 随包，不运行时拉 GitHub；无更好的独立中文源。
- **估值口径** → 默认取**红城近 7 天 `avg_price`**（走 `/history` time-scale=24），红城稀疏回退**多城近 7 天 avg_price 中位**，统一过滤 0 与离群（>中位 3 倍剔除）；`/prices` 现价仅用于 `/物价` 即时查询。
- **大额播报规则** → 固定为击杀/死亡声望大于 100 万，或银币总损失大于 1000 万；`/设置 大额阈值` 仅作旧命令兼容提示，不再改变运行时规则。
- **补装频道** → 新流程使用 `asia-` 前缀的申请、审核、发放、通知四频道；旧 `regear_channel_id` 只做兼容兜底，且配置频道仍需保留当前区服前缀。
- **AI 辅助** → LongCat/OpenAI 兼容接口默认关闭，启用后只走 `/助手`、`/战报`、`/补装解释`，输入为结构化事实包，输出层做危险动作声明拦截和密钥脱敏。
- **版本号控制** → 当前版本 `1.0`，代码单一来源 `bot/version.py`；`/ping` 用同一版本源。
- **战报推送** → 已完成战报聚合、卡片模块、`battle_report_channel_id`、`battle_report_min_guild_players`、最低 20 名本会参战者门槛、持久去重表和 `auto.py` 定时任务；当前仅有离线测试覆盖，后续需要真实 KOOK 活测和线上运行验证。

待定：
- （暂无，上述已收口）
```
