# Progress Log

## Session: 2026-07-02

### Current Status
- **Phase:** 1 → 完成,准备进入 Phase 2 设计定稿
- **Started:** 2026-07-02

### Actions Taken
- 对比 `Albion-EU-kook/bot/` vs `Albion-ASIA-kook/bot/` 全量文件差异
- 读取欧服 `config.py / main.py / tasks/auto.py / tasks/collectors.py / albion/client.py / albion/gameinfo.py / store/db.py / store/repo.py / store/bootstrap.py / region_scope.py`
- 探测商汤 API `token.sensenova.cn/v1`:模型列表 + `deepseek-v4-flash` chat completion 成功
- 用户澄清:合并同时把亚服升级到欧服 M7 全套 → 简化决策

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| 商汤 `/v1/models` GET | 200 + 模型列表 | 200,返回 4 个可用模型 | ✅ |
| 商汤 `/v1/chat/completions` POST `deepseek-v4-flash` | 200 + 中文回复 | 200,回复"好的,收到..." | ✅ |
| 商汤 `deepseek-v3` | 200 | 5 `model is not found` | ⚠️ 期望内 → 换用 `deepseek-v4-flash` |
| 商汤 `GET /models`(无 /v1) | 200 | 7 Forbidden | ⚠️ 期望内 → 走 `/v1/models` |

### Errors
| Error | Resolution |
|-------|------------|
| 无 | — |

### Open Questions(阻塞 Phase 2 定稿)
1. **KOOK 服务器 ID 冲突**:`bootstrap.py` 里欧服 fumass 和亚服 Mika 的 `kook_guild_id` 都写着 `4676167053713576`。这是同一个 KOOK 服务器同时给两个 bot 用(共存),还是两个不同 KOOK 服务器?合并方案完全取决于这个答案:
   - **场景 A**(共存):同一 KOOK 服务器 `4676167053713576` 里,一部分频道 `eu-*` 给欧服 Top Squad,另一部分 `asia-*` 给亚服 Mika → 需要在 `guild_binding` 表加 `region` 列,`kook_guild_id` 联合 `region` 作主键
   - **场景 B**(不同服务器):两个 KOOK 服务器实际是不同 ID,`bootstrap.py` 里的 ID 是同一个只是巧合/复用测试 → 合并简单,直接用 kook_guild_id PK

2. **合并部署形态**:
   - 单 OpenDeploy project + 单容器 + 进程内跑两个 khl.py Bot 实例(共享 SQLite/AlbionClient)
   - 单 OpenDeploy project + 两个 service(EU service + ASIA service),各自独立进程但共享托管 Postgres/Redis
   - 用户提到 OpenDeploy 现在支持托管数据库 + Redis,倾向哪个方案?

3. **战报 `min_guild_players` 下限**:欧服夜间 Top Squad 战斗常态人数是否真的 <20?能否放开到 15 或 10?

### Next
- 等用户回答 3 个 open questions,尤其 (1) KOOK 服务器 ID 冲突问题
- 拿到答复后 Phase 2 出设计定稿(codex 派活前的最终版)

### Phase 3.1 - 仓库合并基线（Codex companion）
- **Status:** complete
- **Branch:** `feat/consolidate-dual-region`
- **Scope:** `bot/config.py` 改为 `AlbionRegionConfig` + `REGION_CONFIGS` 双区配置；`bot/region_scope.py` 删除 `_infer_region_from_config()`，频道 scope helper 支持显式 `region=`；`.env.example` 改为 `*_EU` / `*_ASIA` 样板。
- **Tests:**
  - `.venv/bin/python -m pytest tests/test_config_diagnostics.py tests/test_region_scope.py` → 21 passed
  - `.venv/bin/python -m pytest tests/` → 215 passed
  - `scripts/check.sh` → unittest 215 tests OK + compileall OK
- **Self-review:** staged Phase 3.1 不改 `bot/store/*`、`bot/main.py`、`bot/ai/*`；`rg _infer_region_from_config bot tests .env.example` 无代码命中。当前工作区仍保留接手前 M7/OpenDeploy 未提交改动，未作为 Phase 3.1 范围处理。

### Phase 3.2 - 数据模型 + 进程内双 bot（Codex companion）
- **Status:** complete
- **Branch:** `feat/consolidate-dual-region`
- **Scope:** `bot/store/db.py` 增加 region-aware schema 和幂等迁移；`bot/store/repo.py`、commands、tasks、collectors 和 status API 按 region 显式过滤；`bot/main.py` 增加 `build_bots()`，每区独立 KOOK bot / Albion client，AIService 共享；补齐 EU M7 运行依赖的 attendance、collectors、web/status API 和测试文件。
- **Tests:**
  - `.venv/bin/python -m pytest tests/` → 219 passed
  - `scripts/check.sh` → 219 tests OK + `compileall bot scripts tests` OK
  - `git diff --check` → OK
- **Migration probe:** 临时 SQLite 连续 `init_db()` 3 次、分别 seed `eu` / `asia`、再重复 `init_db()` 2 次后，`SELECT region, COUNT(*) FROM guild_binding GROUP BY region` 返回 `asia:1,eu:1`；关键表 PK 复查为 `guild_binding(kook_guild_id,region)`、`player_binding(kook_user_id,kook_guild_id,region)`、`battle_snapshot(kook_guild_id,region,battle_id)`、`battle_report_seen(kook_guild_id,region,battle_id)`、`high_fame_event(kook_guild_id,region,event_id)`、`collector_cursor(name,kook_guild_id,region)`。
- **Self-review:** `git diff -- bot/ai` 无输出；`rg "contextvars|global REGION|CURRENT_REGION" bot` 无输出；未改 Phase 3.4 延迟参数和 `_seen`/`event_broadcast_seen` 策略，`BATTLE_REPORT_MIN_PLAYERS=20`、`MAX_BROADCAST_PER_TICK=15`、`FEED_PAGES=4` 仍保持原值。本阶段未启动真实 bot、未做 KOOK `/ping` 活测，真实双 token 日志和频道响应留到 Phase 5 部署冒烟。
