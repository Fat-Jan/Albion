# 阿尔比恩公会 KOOK 机器人 — 实现计划

> 配套文档：`阿尔比恩数据接口文档.md`（数据源、端点、字段、估值逻辑都在那）
> 本计划假设：旧的 React 前端 + Node backend 已归档不再维护 → 新项目走**单一 Python 自包含**，不依赖旧 backend。

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
| `gameinfo.events(guildId)` | `/events?guildId=` | 死亡播报 + 出勤快照 |
| `gameinfo.fame()` | `/events/playerfame`·`/players/statistics` | 声望榜（PvP/PvE） |
| `gameinfo.battles(guildId)` | `/battles?guildId=` (+`/events/battle/{id}`) | 出勤统计（参战者聚合） |
| `market.prices(types, q)` | AODP `/api/v2/stats/prices/{items}.json` | 物价即时查询（`/物价`） |
| `market.history(types)` | AODP `/api/v2/stats/history/{items}.json?time-scale=24` | 估值口径：近 N 天各城 avg_price |
| `market.gold()` | AODP `/api/v2/stats/gold.json` | 金价 |

要点（来自接口文档实测）：
- 区服一致：战斗 `gameinfo-sgp`、市场 `east.albion-online-data.com`、ZvZ `api.albionbb.com/asia`。
- 先 `/search` 拿 ID 再查详情。
- AODP 限流 **180/分**，批量逗号查 + 本地缓存价格。
- 亚服挂单稀疏 + 离群噪音 → 估值取多城中位/最低正价，或用 `/history` 近 N 天均价兜底。
- 不可交易物（技能书等）查不到价 → 跳过记 0。
- 官方 API 偶发故障 → 全部调用要容错 + 退避。

估值逻辑直接搬接口文档第七节（10 槽 Equipment + Inventory 数组 → AODP 累加）。

---

## 五、验证流程（方案二：名字匹配 + 管理员审批）

```
玩家 /绑定 <角色名>
   │
   ├─ search + players/{id} 查角色
   │     ├─ 角色不存在 → 直接拒，提示
   │     └─ 角色.GuildId != 本服已绑公会 → 直接拒，提示"该角色不在本公会"
   │
   └─ 命中 → KOOK 角色预检（信心分级，非硬门槛）
              ├─ 已持「可信身份组」(管理员配置) → 快速通道，可自动通过
              └─ 无可信身份组 → 「审批频道」发待审批卡片(含角色名/IP/公会)
                                  管理员点 [通过] / [拒绝] 按钮
                 通过 → 发会员身份组 + 改 KOOK 昵称为角色名 + 落库 player_binding
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
  kook_guild_id     TEXT PRIMARY KEY,
  albion_guild_id   TEXT NOT NULL,
  albion_guild_name TEXT NOT NULL,
  member_role_id    TEXT,          -- 绑成功后发的身份组
  approval_channel_id TEXT,        -- 审批卡片发到哪
  created_by, created_at
)

-- 玩家绑定
player_binding(
  kook_user_id      TEXT,
  kook_guild_id     TEXT,
  albion_player_id  TEXT NOT NULL,
  albion_player_name TEXT NOT NULL,
  status            TEXT,          -- verified
  bound_at,
  PRIMARY KEY (kook_user_id, kook_guild_id)
)

-- 待审批
pending_approval(
  id INTEGER PRIMARY KEY,
  kook_guild_id, kook_user_id,
  albion_player_id, albion_player_name,
  message_id        TEXT,          -- 审批卡片消息 ID
  status            TEXT,          -- pending/approved/rejected
  created_at
)

-- 补装申请
regear_request(
  id INTEGER PRIMARY KEY,
  kook_guild_id, kook_user_id,
  albion_player_id,
  event_id          TEXT,          -- 关联的死亡事件
  est_value         INTEGER,       -- /估值 算出的银币
  message_id        TEXT,          -- 申请卡片消息 ID
  status            TEXT,          -- pending/approved/rejected/paid
  created_at, reviewed_by, reviewed_at
)
```

---

## 七、指令清单

**管理员**（发起人身份组需 ≥ 频道管理员，用 KOOK 角色权限位校验）
- `/绑定公会 <公会名>` → search 列候选 → 按钮选中 → 落库
- `/设置 会员身份组 @身份组`
- `/设置 审批频道 #频道`
- `/设置 大额阈值 <fame>`  → 死亡播报高亮门槛，默认 100k fame，可调
- `/解绑公会`

**玩家**
- `/绑定 <角色名>` → 走第五节审批流
- `/解绑`

**查询**（已绑定用户免输名字）
- `/战绩 [角色名]` → 玩家档案 + KD + 最近击杀/死亡
- `/估值` → 最近一次死亡的装备+背包估值（AODP）
- `/战役` → 公会最近 ZvZ 战报（albionbb/asia 或官方 `/battles?guildId=`）
- `/物价 <物品>` → AODP 现价
- `/金价` → AODP `gold.json`，近 24h 价格与波动
- `/榜单 [pvp|pve]` → 声望榜：PvP `/events/playerfame`、PvE `/players/statistics?type=PvE`
- `/补装` → 选最近死亡 → 复用 `/估值` → 发申请卡片到管理频道 → 管理员 [通过]/[拒绝] → 记账（落 regear_request）
- `/出勤` → 最近 N 场 `/battles?guildId=` 聚合参战者，出成员出勤快照（趋势版需采集器，归二期）

**自动（一期，与查询同期落地）**
- 死亡播报：定时轮询 `/events?guildId=` → 推卡片到播报频道
  - 区分**我方击杀 / 我方阵亡**；`TotalVictimKillFame` 超阈值的**大额击杀单独高亮**推送
  - 注意 KOOK 每日发消息上限 1 万，控频 + 去重
- 退会复查：每日比对 `/guilds/{id}/members` → 退会自动撤销身份组
- 两者共用同一套 asyncio 定时轮询骨架（同一循环 + 容错退避），合做省一套调度

---

## 八、项目结构

```
albion-kook-bot/
├── bot/
│   ├── main.py              # khl.py Bot 启动 + WS 连接
│   ├── config.py            # env: KOOK_TOKEN 等
│   ├── commands/
│   │   ├── admin.py         # 绑定公会 / 设置
│   │   ├── register.py      # 玩家绑定 + 审批（含 KOOK 角色预检分级）
│   │   ├── query.py         # 战绩 / 估值 / 战役 / 物价 / 金价 / 榜单 / 出勤
│   │   └── regear.py        # 补装申请 + 审批记账
│   ├── cards/               # 卡片构建（选公会、审批、战绩、估值、补装、播报）
│   ├── tasks/               # 定时轮询：死亡播报 + 退会复查（共用调度骨架）
│   ├── albion/
│   │   ├── client.py        # httpx + 缓存 + 限流 + 退避
│   │   ├── gameinfo.py      # search/players/guilds/events/battles/fame
│   │   ├── market.py        # AODP prices + gold
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
| **M0 脚手架** | khl.py 连上 KOOK WS，`/ping` 回 `pong` | 频道发 `/ping` 收到回复 |
| **M1 数据层** | `albion/client+gameinfo+market+valuation` | 对真实角色名跑通：返回档案、估值为非负数 |
| **M2 公会绑定** | `/绑定公会` 权限校验 + search + 按钮选中 + 落库 | 非管理员被拒；管理员绑成功且 DB 有记录 |
| **M3 玩家绑定+审批** | `/绑定` → 审批卡片 → 按钮通过 → 发组+改名 | 不在公会的角色被拒；在公会的走审批后拿到身份组 |
| **M4 查询指令** | `/战绩 /估值 /战役 /物价 /金价 /榜单` | 已绑定用户免输名字直接出结果 |
| **M5 补装** | `/补装` → 选死亡 → 复用估值 → 申请卡片 → 批准记账 | 申请走审批后 regear_request 落 approved |
| **M6 自动任务** | 死亡播报（分击杀/阵亡+大额高亮）+ 退会复查 | 公会有死亡时频道收到卡片；大额单独高亮；退会成员身份组被撤 |
| **M7 出勤（快照）** | `/出勤` 最近 N 场参战者聚合 | 出成员出勤次数快照（趋势版+采集器归二期） |

---

## 十、风险与注意

1. **所有权验证非强保证** —— 方案二靠管理员人眼，接受冒名残余风险；后续要更强可加"改名挑战"。
2. **官方 API 偶发故障**（社区常态）—— 所有调用容错 + 退避，失败给友好提示而非崩。
3. **亚服市场稀疏 + 离群噪音** —— 估值做兜底（多城中位/历史均价），不取单点。
4. **KOOK 每日发消息上限 1 万** —— 死亡播报要控频 + 去重，避免刷爆配额。
5. **Token 安全** —— 走 env，不入库不进 git；`.env` 加 `.gitignore`。
6. **区服别混** —— 战斗 sgp / 市场 east / ZvZ asia，三者都得是亚服。

---

## 十一、决议 / 下一步

已收口（2026-06-14）：
- **死亡播报 + 退会复查** → 一期一起做（共用定时轮询骨架，见第七节、M5）。
- **估值默认口径** → 红城（Caerleon）卖单最低正价，过滤 0/离群；缺数据回退多城中位或 `/history` 近 N 天 `avg_price`。同类 bot（bridgewatcher 等）默认即红城/黑市价。展示标注「按红城均价估算」。
- **所有权验证** → 加 KOOK 角色预检做信心分级（已持可信身份组+API 命中可快速通过），非硬门槛，见第五节。

- **功能盘缺口**（对比同类 bot 收口）→ 一期补：`/金价`、`/榜单`、死亡播报分击杀/阵亡+大额高亮、`/补装`（复用估值+审批）；`/出勤`一期只做最近 N 场快照，趋势版+采集器归二期。明确不做：经济/虚拟银行/税、CTA 排期、运输套利、武器对战矩阵。
- **物品中文名** → 一期接 ao-bin-dumps（唯一权威源，`LocalizedNames["ZH-CN"]`），预处理成本地 dict 随包，不运行时拉 GitHub；无更好的独立中文源。
- **估值口径** → 默认取**红城近 7 天 `avg_price`**（走 `/history` time-scale=24），红城稀疏回退**多城近 7 天 avg_price 中位**，统一过滤 0 与离群（>中位 3 倍剔除）；`/prices` 现价仅用于 `/物价` 即时查询。
- **大额阈值** → 不硬编码，做成 `/设置 大额阈值 <fame>`，默认 100k fame，管理员按公会战力自调。

待定：
- （暂无，上述已收口）
```
