# Task Plan: 合并欧服/亚服 Bot + 换商汤 AI + 修复延迟

## Goal
把 `Albion-EU-kook` 和 `Albion-ASIA-kook` 两个仓合并成单容器、单进程、双 bot 实例的部署形态,继续用 SQLite(不引入 Postgres/MySQL/MongoDB/Redis,数据量太小、单进程无并发需求);亚服合并顺便升级到欧服的 M7 全套(出勤/collectors/web dashboard);AI 模块从已停止免费的 OpenAI 兼容旧 AI 服务 迁移到商汤 `deepseek-v4-flash`;修复击杀/阵亡播报 5-10 分钟延迟和夜间战报静默问题。

## Current Phase
Phase 2 已定稿 → 待用户派 codex 执行 Phase 3.1/3.2/3.3/3.4。
4 段 codex prompt 在 findings.md "Codex 派活 Prompt" 章节,可直接复制粘贴。

## Handoff Model
**主 agent(Claude Code)只负责**:需求梳理、决策拍板、写死计划文件、生成 codex 派活 prompt。
**Codex companion 全包**:代码改动、单测、self-review、跑 `scripts/check.sh`、OpenDeploy 部署、上线后冒烟。
主 agent 交付物 = 计划三件套(task_plan.md / findings.md / progress.md)+ 4 段可直接粘贴的 codex prompt。之后主 agent 不再介入,除非 codex 反馈计划里有漏洞。

## Phases

### Phase 1: Requirements & Discovery ✅
- [x] 用户三大诉求已解析:合仓 / 换 AI / 修延迟
- [x] 双仓代码 diff 已跑,差异清单在 findings.md
- [x] SenseNova API 已探针,`deepseek-v4-flash` 可用,key 有效
- [x] 播报延迟根因初判在 findings.md
- **Status:** complete

### Phase 2: Planning & Structure ✅
- [x] 三个关键决策由用户拍板(见 Decisions Made)
- [x] 数据模型改动方案定稿(`region` 列 + 复合 PK)
- [x] 进程内双 bot 拓扑图定稿
- [x] 战报门槛下调到 10 定稿
- [x] AI 迁移只改 env、不改代码定稿
- **Status:** complete

### Phase 3: Implementation
分 4 个可独立派 codex 的子任务。执行顺序 3.1 → 3.2 → 3.3 → 3.4,3.3/3.4 可并行。

#### Phase 3.1: 仓库合并基线 (codex #1)
- [ ] 以 `Albion-EU-kook` 的 `deploy/eu` 分支为主线(M7 全套已在)
- [ ] 从 `Albion-ASIA-kook` 仅同步差异:`bot/config.py` 的 asia 默认值不再需要(改成 region 表)、`kill_fame_threshold=400000` 已在 `bootstrap.py::RUNTIME_GUILD_CONFIGS["asia"]` 里,不用再搬
- [ ] 删除 `region_scope._infer_region_from_config()` 依赖(未来 region 由 guild_binding 表决定,不再由 env 单值决定)
- [ ] 保留双仓 `.env.example` 里所有 region-specific 变量,但 config.py 读法从"单值"改成"region-keyed dict"
- **验收**:合并后 `python -m pytest tests/` 全绿,`scripts/check.sh` 通过
- **Status:** pending

#### Phase 3.2: 进程内双 bot + region 隔离数据模型 (codex #2,大改)
- [ ] `bot/store/db.py`:给 `guild_binding` 加 `region TEXT NOT NULL DEFAULT 'eu'`,复合 PK `(kook_guild_id, region)`(SQLite 不能直接改 PK,要 `CREATE TABLE ... _new` → 拷贝 → drop 旧表 → rename)
- [ ] 相同处理:`player_binding`(PK 变 `(kook_user_id, kook_guild_id, region)`)、`battle_snapshot`、`battle_participant`、`guild_member_snapshot`、`battle_report_seen`、`high_fame_event`、`collector_cursor`
- [ ] 迁移脚本:老库自动 backfill,`region` 从环境变量当次值或 `bootstrap.py::_infer_region_from_config()` 反推
- [ ] `bot/store/repo.py`:所有以 `kook_guild_id` 为 key 的函数改成 `(kook_guild_id, region)`,`all_guild_bindings()` 可选 region 过滤
- [ ] `bot/config.py`:抽出 `AlbionRegionConfig` dataclass,顶层保留一个 `REGION_CONFIGS: dict[str, AlbionRegionConfig]` 字典;env 保留双区分开变量(`GAMEINFO_BASE_EU`/`GAMEINFO_BASE_ASIA`,兼容单值旧变量)
- [ ] `bot/main.py`:改成 `build_bots()` 返回 `list[Bot]`,每个 Bot 有独占 token、独占 `AlbionClient/GameInfo/Market`、独占 `region_code`,共享 `AIService`(有状态但线程/协程安全)和 SQLite pool
- [ ] `bot/tasks/auto.py`:所有 `all_guild_bindings()` 遍历改成按 region 过滤,避免 EU bot 处理 ASIA 公会
- [ ] KOOK 频道路由:两个 bot 都会收到同一个 KOOK 服务器所有消息,靠 `region_scope.should_process_message()` 按频道前缀(eu-/asia-)决定处理不处理 —— 这块已经在,只需确认 region_code 由 Bot 实例注入不由全局 env
- [ ] `web/status_api.py`:dashboard 侧展示时按 region 分组
- **验收**:双 bot 启动后各自 `bot_id=49050/49025` token_fp `2262e4d75d7b/45a5a99e7b1b` 都在日志出现,`select region, count(*) from guild_binding` 返回两行,`/ping` 在 `eu-` 频道由 EU bot 响应、`asia-` 频道由 ASIA bot 响应
- **Status:** pending

#### Phase 3.3: AI 迁移到商汤 (codex #3,轻改)
- [ ] `.env.example`:新增/更新
  - `AI_BASE_URL=https://token.sensenova.cn/v1`
  - `AI_API_KEY=sk-xxx`(实际值不入 git,只写 example 占位)
  - `AI_MODEL=deepseek-v4-flash`(推荐:1M context / 中文强 / 免费 / 支持 tools;备选 `glm-5.2` 长上下文更强但推理慢)
- [ ] `bot/ai/client.py`:确认 `chat_completions_url` 逻辑对 base_url 结尾 `/v1` 的处理无 bug(现有代码已支持,验证一下)
- [ ] `bot/config.py`:`AI_BASE_URL` 默认值改成 `https://token.sensenova.cn/v1`(原来是 `旧 AI endpoint`)
- [ ] `bot/ai/service.py`:`deepseek-v4-flash` 支持 reasoning,响应会带 `reasoning_content` 字段,现有 `data["choices"][0]["message"]["content"]` 提取路径不变,但要单测确认长 reasoning 不会撑爆 `AI_MAX_OUTPUT_TOKENS=800`;可能需要提高到 2000
- [ ] 现网 `.env`:两个远端(EU/ASIA)分别 rewrite `AI_BASE_URL/AI_API_KEY/AI_MODEL`,重启服务
- [ ] tests:新增 `tests/test_ai_sensenova.py`,`MockTransport` 返回带 `reasoning_content` 的响应,验证只取 `content`
- **验收**:探针 `curl -sS -X POST https://token.sensenova.cn/v1/chat/completions -H "Authorization: Bearer $KEY" ...` 200;`/助手` 和 `/战报` 真实 KOOK 交互能出摘要;日志无 `AI 请求失败`
- **Status:** pending

#### Phase 3.4: 延迟修复 (codex #4,精修)
诊断结果(详见 findings.md):
- 死亡播报间隔本身 90s/60s 不是主凶
- 5-10 分钟延迟根因组合:(a) 官方 `/events` 全局 feed 有 30s TTL 缓存 + (b) `FEED_PAGES=4 × 51 = 204` 条,忙时段可能不够;(c) `MAX_BROADCAST_PER_TICK=15` 忙时段积压会跨多轮才播完;(d) `_seen` 仅内存,重启丢
- 战报夜间静默主凶:`_effective_battle_report_min_guild_players()` 强制 `max(20, configured)`,configured 存 5 也被抬到 20

改动:
- [ ] `bot/tasks/auto.py::BATTLE_REPORT_MIN_PLAYERS`:20 → 10
- [ ] `bot/tasks/auto.py::_effective_battle_report_min_guild_players`:改成 `max(10, configured)`,让 configured=10 生效(configured 存的是 `battle_report_min_guild_players`)
- [ ] `bot/tasks/auto.py::MAX_BROADCAST_PER_TICK`:15 → 30(单轮承载更多积压)
- [ ] `bot/tasks/auto.py::FEED_PAGES`:忙时段(20:00-00:30)动态提高到 6,普通时段保持 4
- [ ] `bot/albion/client.py::gameinfo_get` 对 `/events` 路径的 `ttl` 参数确认(gameinfo.py `events()` 传 `ttl=30`,合理;不改)
- [ ] `bot/tasks/auto.py::_seen`:改用 SQLite 持久去重(复用 `battle_report_seen` 模式,新建 `event_broadcast_seen` 表),重启不丢
- [ ] `bot/tasks/auto.py::death_broadcast` 加详细日志:每轮记 `fetched_events / new_events / broadcasted / skipped_by_region_scope`,方便下次调参
- **验收**:重启后 5 分钟内新击杀事件能推;夜间小规模(10-19 人)战报能推;`grep '播报达单轮上限' bot.log` 频次显著下降
- **Status:** pending

### Phase 4: Testing & Verification (codex 自审)
- [ ] codex 自审 diff:每个 phase 交付前跑 `python -m pytest tests/` 全绿 + `scripts/check.sh` 通过
- [ ] codex adversarial self-review:验证合仓后没把亚服/欧服的 albion_guild_id 混掉;`region_scope.CURRENT_REGION` 不能残留跨请求
- [ ] `.opendeploy` 目录已在 gitignore,重新起 project 前 dry run
- **Status:** pending — **由 codex 负责**

### Phase 5: Delivery (codex 部署)
- [ ] OpenDeploy 新 project `albion-kook-merged` + service `web` 起来(或复用 EU 现有 project `32e65f76-29f3-401c-8c59-b689761f768d`,更改 service 名并加 ASIA env)
- [ ] 挂载 1Gi 持久卷 `/app/data`(EU 老 volume 迁过来,或新建后 backfill)
- [ ] 环境变量按 region-keyed 命名注入(`KOOK_TOKEN_EU/KOOK_TOKEN_ASIA`,`GAMEINFO_BASE_EU/GAMEINFO_BASE_ASIA` 等)
- [ ] `/healthz` 200、`/api/status` 200 且两个 region 的 collector_summary 都 ok
- [ ] 亚服现有 project `albion-asia-kook` 停机(先保留 30 天防回滚)
- [ ] 真实 KOOK 交互复测:欧服 `/ping` in `eu-` 频道、亚服 `/ping` in `asia-` 频道,分别拿到 `pong v1.0` 和不同 bot 头像
- **Status:** pending — **由 codex 负责**

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 欧服代码为合并基准,亚服升级到 M7 全套 | EU 已有 attendance/collectors/web/status_api;亚服仅缺"顺便同步"的差异,合并时一次到位 |
| KOOK 同一服务器共存两个 region | 用户确认 fumass(Top Squad EU)和 Mika(ASIA)都在 `4676167053713576`;必须给 guild_binding 加 region 列做联合 PK |
| 单容器 + 单进程内双 bot 实例 | 省 OpenDeploy 配额;两个 bot 各持独立 token 独立 WebSocket,共享 SQLite/AIService;进程 crash 双区一起挂但可接受 |
| AI 换商汤 `deepseek-v4-flash` | 已探针成功,OpenAI 兼容,1M context,中文强,支持 tools,当前 pricing=0 免费;备选 `glm-5.2`(推理更强但慢) |
| 战报 min_guild_players 从 20 下调到 10 | 用户确认小规模场次(10-19 人)也要推;去掉 `max(20, configured)` clamp |
| 死亡播报改 SQLite 持久去重 | 内存 `_seen` 重启就丢,是延迟的一个诱因(重启后 `_primed` 阶段直接吞事件) |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| (none yet) | |
