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

### Phase 3.3 - AI 迁移到商汤（Codex companion）
- **Status:** complete
- **Branch:** `feat/consolidate-dual-region`
- **Scope:** `bot/config.py` 默认 AI provider 改为 SenseNova OpenAI-compatible endpoint：`AI_BASE_URL=https://token.sensenova.cn/v1`、`AI_MODEL=deepseek-v4-flash`、`AI_MAX_OUTPUT_TOKENS=2000`；`.env.example` 更新为商汤占位配置，并移除旧兼容 AI key fallback；`bot/ai/client.py` / `bot/ai/__init__.py` 去除 OpenAI 兼容旧 AI 服务 默认文案；新增 `tests/test_ai_sensenova.py`，并补充配置默认值测试。
- **TDD notes:** 目标测试首次运行时 `test_ai_defaults_use_sensenova_deepseek_flash` 失败，实际默认仍为 `旧 AI endpoint`；生产改动后目标验证 `.venv/bin/python -m pytest tests/test_config_diagnostics.py::ConfigDiagnosticsTest::test_ai_defaults_use_sensenova_deepseek_flash tests/test_ai_sensenova.py tests/test_ai_module.py::AIClientTest::test_ai_client_uses_sensenova_v1_url_and_ignores_reasoning_content` → 3 passed。
- **Tests:**
  - `.venv/bin/python -m pytest tests/` → 222 passed
  - `scripts/check.sh` → 222 tests OK + `compileall bot scripts tests` OK
  - `git diff --check` → OK
- **External probe:** 当前 shell 未注入 `AI_API_KEY`，未读取 `.env` 密钥，真实 `curl https://token.sensenova.cn/v1/chat/completions` 留到 Phase 5 env 注入后执行。代码级 MockTransport 已验证 base_url 结尾 `/v1` 时请求路径为 `/v1/chat/completions`，且只返回 `message.content`、忽略 `reasoning_content`。
- **Self-review:** `git diff -- bot/store bot/tasks/auto.py` 无输出，未越界修改 Phase 3.2/3.4 文件；已扫描计划、示例环境和代码中的 secret-like 字符串，未发现真实 key，README/使用说明书仍有 OpenAI 兼容旧 AI 服务 旧文案但属于接手前未提交文档改动，未纳入 Phase 3.3 提交范围。

### Phase 3.4 - 延迟修复（Codex companion）
- **Status:** complete
- **Branch:** `feat/consolidate-dual-region`
- **Scope:** `bot/tasks/auto.py` 将战报最低本会人数下限降到 10、忙时段 feed 页数提高到 6、单轮播报上限提高到 30，并为死亡播报增加 fetched/new/broadcasted/skipped_by_region 日志；`bot/store/db.py` / `bot/store/repo.py` 增加 `event_broadcast_seen(kook_guild_id, region, event_id)` 持久去重；runtime seed 默认 EU/ASIA `battle_report_min_guild_players=10`；补充战报阈值、忙时段扩页、单轮 30 条和 SQLite region 去重测试。
- **Tests:**
  - `.venv/bin/python -m pytest tests/` → 226 passed
  - `scripts/check.sh` → unittest 226 tests OK + `compileall bot scripts tests` OK
  - `git diff --check` → OK
- **Self-review:** `git diff -- bot/ai` 无输出，未越界修改 Phase 3.3；`rg "event_broadcast_seen|has_seen_event_broadcast|mark_event_broadcast_seen" bot tests` 显示 schema、repo API、auto 调用和测试均带 region；`git -C /Users/arm/Desktop/vscode/Albion-ASIA-kook status --short --branch` 只读检查显示参考仓已有脏文件，本阶段未写入 ASIA 仓；未启动真实 bot、未做 KOOK 活测，5 分钟内新击杀、夜间 10-19 人战报和线上日志频次下降留到 Phase 5 部署冒烟验证。

### PR / Phase 5 - Delivery handoff（Codex companion）
- **Status:** PR opened, deployment blocked on safe secret + SQLite export path.
- **PR:** https://github.com/Fat-Jan/Albion/pull/1 (`feat/consolidate-dual-region` → `main`)
- **Verification before PR:**
  - `.venv/bin/python -m pytest tests/` → 226 passed
  - `scripts/check.sh` → unittest 226 tests OK + `compileall bot scripts tests` OK
  - `git diff --check 4a77efc..HEAD` → OK
  - `git diff --check` → OK
  - `git diff --cached --check` → OK
  - committed secret scan found no SenseNova/KOOK secrets; only `Bearer test-key` test fixture matched broad bearer regex.
- **OpenDeploy read-only probe:** `opendeploy context resolve --json` points existing EU project `32e65f76-29f3-401c-8c59-b689761f768d`, service `cd6868e9-cb87-47dd-ba88-0c56a995f59c`, live URL `https://cd6868e9.opendeploy.site`; `opendeploy deploy plan . --review --json` is ready with Dockerfile port 8080 and no blocking issues; `opendeploy preflight . --json` is blocked by OpenDeploy skill/plugin policy, not by code plan.
- **Deployment blockers:** EU and ASIA OpenDeploy services still expose old single-region env keys only through redacted CLI output; region-keyed secrets (`KOOK_TOKEN_EU`, `KOOK_TOKEN_ASIA`, SenseNova `AI_API_KEY`) cannot be safely derived without an approved secret source. Both services have `/app/data` volumes, but `opendeploy routes list --json` shows volume list/add/resize/detach/restore/delete only, with no confirmed safe file export or container exec path to dump and merge SQLite.
- **Not done:** no OpenDeploy redeploy, no SQLite merge, no KOOK `/ping` live smoke, and no old EU/ASIA project stop. Keep old projects running until the safe migration path is confirmed.

### Phase 5 - OpenDeploy merged deployment smoke（Codex companion）
- **Status:** partially complete; OpenDeploy deploy/API smoke passed, KOOK 真人 `/ping` 活测未完成。
- **Deployment:** 复用 EU project `32e65f76-29f3-401c-8c59-b689761f768d` / service `cd6868e9-cb87-47dd-ba88-0c56a995f59c`，deployment `d3a2f7d3-b6b5-4ee2-9291-d7eb84f380ec` / version `1.0.3`，`status=success`、`is_current=true`、完成于 `2026-07-01T22:45:12Z`。本轮未重新上传新包。
- **OpenDeploy control plane:** `opendeploy deployments get d3a2f7d3-b6b5-4ee2-9291-d7eb84f380ec --json` 返回 `status=success`、`is_current=true`、`progress=100`；`opendeploy services get cd6868e9-cb87-47dd-ba88-0c56a995f59c --json` 返回 service `status=running`、Dockerfile builder、`start_command=python -m bot.main`、`port=8080` locked、`external_url=https://cd6868e9.opendeploy.site`、`/app/data` 1Gi volume `albion-eu-data` active；`opendeploy deploy plan . --review --json` 返回 `status=ready`、`blocking_issues=[]`。runtime variable key 包含 `KOOK_TOKEN_EU`、`KOOK_TOKEN_ASIA`、`GAMEINFO_BASE_EU`、`GAMEINFO_BASE_ASIA`、`AODP_BASE_EU`、`AODP_BASE_ASIA`、`ALBIONBB_BASE_EU`、`ALBIONBB_BASE_ASIA`、`AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`、`AI_MAX_OUTPUT_TOKENS`，未使用 `--show-secrets`，未读取密钥原文。
- **Public smoke:** 2026-07-02 07:08 CST 复测，`curl -A 'Mozilla/5.0 CodexSmoke/1.0' https://cd6868e9.opendeploy.site/healthz` 返回 HTTP 200 `ok`；`/api/status` 返回 version `1.0`、`last_heartbeat=2026-07-01T23:07:57Z`、`last_task_run=2026-07-01T23:05:02Z`、top-level collector_summary `ok` total 6，`regions.eu` 与 `regions.asia` collector_summary 均为 `ok` total 3；`/api/attendance/recent?limit=2` 返回 2 条且 regions 为 `asia,eu`；`/api/invites` 返回 `eu=""`、`asia=""`；`/api/market/gold?limit=2` 返回 1 组快照，`captured_at=2026-07-01T23:00:02Z`。
- **Fresh recheck:** 2026-07-02 07:16 CST 复核 deployment 仍为 `status=success`、`is_current=true`、service `status=running`；`/healthz` 返回 `ok`，`/api/status` 返回 `last_heartbeat=2026-07-01T23:16:24Z`、`last_task_run=2026-07-01T23:15:02Z`、top-level collector_summary `ok` total 6，EU/ASIA 两区 collector_summary 均为 `ok` total 3；未使用 `--show-secrets`，未读取密钥原文。
- **Final recheck:** 2026-07-02 07:21 CST 复核 `opendeploy deployments get ... --json` 仍为 `status=success`、`is_current=true`、`progress=100`；`opendeploy services get ... --json` 返回 service `status=running`、`deployment_version=1.0.3`、`port=8080` locked、`/app/data` volume active；公网 `/healthz` 返回 `ok`，`/api/status` 返回 `last_heartbeat=2026-07-01T23:21:43Z`、`last_task_run=2026-07-01T23:20:02Z`、top-level collector_summary `ok` total 6，EU/ASIA 两区 collector_summary 均为 `ok` total 3；`.venv/bin/python -m pytest tests/` 226 passed，`scripts/check.sh` 226 tests OK + compileall OK，`git diff --check` OK；secret/旧 AI 兼容残留扫描未命中。
- **Runtime logs:** 新 pod `d3a2f7d3` 日志显示 `region=eu bot_id=49050 token_fp=2262e4d75d7b token_source=environment` 与 `region=asia bot_id=49025 token_fp=45a5a99e7b1b token_source=environment` 同时启动，两个 `khl.receiver: [ init ] launched`；seeded runtime guild config 分别为 EU `Top Squad` 与 ASIA `Mika`；日志出现 `gameinfo-ams` 与 `gameinfo-sgp` 请求；错误扫描未命中 `ERROR` / `Traceback` / `Exception` / `failed`，`matches=0`。
- **Monitoring note:** `opendeploy monitoring project-health` 返回 service `status=running` 但 `health_status=unknown`、`ready_replicas=0`；以公网 HTTP、service 状态和 runtime 日志为本轮可用性证据，内置探针待后续单独接入。
- **Not done:** 未做旧 EU/ASIA SQLite 历史合并（用户已确认“不要历史了 后面慢慢补充”）；未停止旧 ASIA project；未完成 EU/ASIA 频道真人 `/ping`，bot token 不能伪装真实用户触发自身命令，日志中也未发现部署后 `/ping`/`pong` 记录。
