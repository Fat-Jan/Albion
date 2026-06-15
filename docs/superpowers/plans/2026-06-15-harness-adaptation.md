# 轻量 Harness 适配实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 Albion KOOK 机器人补齐项目级 harness：固定接手入口、统一离线验证门禁、当前状态落点和安全调试边界。

**架构：** 不重构业务代码，不引入复杂 CI。新增项目入口 `AGENTS.md`、本地验证脚本 `scripts/check.sh`、状态文件 `STATUS.md`，并把 README/notepad 指向这些 truth 文件。验证脚本只跑离线门禁，不启动 bot、不读取 `.env` 内容、不触碰线上服务。

**技术栈：** Python 3.13 venv、unittest、compileall、POSIX shell、Markdown。

---

## 文件结构

- 创建：`AGENTS.md`
  - 项目级接手入口。记录必须先读的文件、禁止泄露密钥、同 token 调试约束、业务边界、验证命令。
- 创建：`scripts/check.sh`
  - 本地离线验证门禁。顺序运行单元测试和编译检查，输出清晰阶段标题。
- 创建：`STATUS.md`
  - 当前项目状态、下一步、阻塞、最近验证证据。只放短事实，不替代 README 和 notepad。
- 修改：`README.md`
  - 在“当前状态”和“测试”区域增加 harness 入口和统一验证脚本说明。
- 修改：`notepad.md`
  - 在 `## Priority Context` 增加一条：项目已采用轻量 harness，后续接手先读 `AGENTS.md` 和 `STATUS.md`。
- 不修改：`.gitignore`
  - `scripts/check.sh` 不产生输出文件，现有忽略规则已覆盖 `.env`、数据库、日志和缓存。

## 当前前置事实

- 本地 venv：`.venv/`
- 当前离线验证命令：
  - `.venv/bin/python -m unittest discover -s tests -v`
  - `.venv/bin/python -m compileall bot scripts tests`
- 最近顺序验证结果：75 个单测通过，`compileall bot scripts tests` 通过。
- 安全边界：`.env` 内有真实 KOOK/AI 密钥，执行计划时不要读取、打印、复制或提交 `.env` 内容。
- 工作区已有业务改动。实现 harness 时只碰本计划列出的文件，避免混入业务修复。

## 任务 1：新增项目级 AGENTS.md

**文件：**
- 创建：`AGENTS.md`

- [ ] **步骤 1：创建项目入口文件**

写入：

````markdown
# AGENTS.md - Albion KOOK Bot 项目规则

## 接手顺序

1. 先读本文件。
2. 再读 `STATUS.md` 获取当前阶段、下一步和最近验证。
3. 非一次性任务再读 `notepad.md` 的 `## Priority Context`。
4. 功能和运维说明以 `README.md`、`使用说明书.md`、`KOOK机器人实现计划.md` 为准。

## 项目定位

- 这是面向单个亚服公会的 KOOK 机器人。
- 技术栈固定为 Python + khl.py + httpx + SQLite。
- 数据源固定为亚服：`gameinfo-sgp`、AODP `east`、albionbb `asia`。
- 当前线上服务在阿里云新加坡 `aliyun_singapore` 的 `albion-kook.service`。

## 安全边界

- 不要读取、输出、复制或提交 `.env` 中的密钥原文。
- `.env`、SQLite 数据库、日志、备份目录都不得提交。
- 日志和汇报只能使用 token 指纹、bot_id、token_source 等脱敏诊断。
- AI 只能走只读辅助链路，不得自动审批绑定、补装、发组、撤组、改金额或标记发放。

## 本地与线上调试

- 同一个 `KOOK_TOKEN` 不能同时被本地 bot 和线上 systemd 服务使用。
- 如果本地 `.env` 使用线上旧 token，必须确保服务器 `albion-kook.service` 已停止后再本地启动 bot。
- 升级服务器代码时不要替换服务器上的旧 `KOOK_TOKEN`。
- 离线验证不得启动 `bot.main`，只跑测试和编译检查。

## 验证门禁

默认离线门禁：

```bash
scripts/check.sh
```

等价命令：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall bot scripts tests
```

涉及 KOOK 交互、真实 API、systemd 或数据库清理时，必须在 `STATUS.md` 或 `notepad.md` 记录验证证据和未验证原因。

## 修改原则

- 外科手术式修改，只碰任务相关文件。
- 不覆盖用户已有改动。
- 业务事实和阶段状态优先写项目内 truth 文件，不写进全局规则。
- 离线验证通过只能说明代码门禁通过，不能宣称 KOOK 真实交互已上线验证。
````

- [ ] **步骤 2：检查文件内容**

运行：

```bash
sed -n '1,220p' AGENTS.md
```

预期：包含“接手顺序”“安全边界”“验证门禁”“修改原则”，且没有任何密钥原文。

- [ ] **步骤 3：Commit**

```bash
git add AGENTS.md
git commit -m "docs: add project harness entry"
```

## 任务 2：新增统一离线验证脚本

**文件：**
- 创建：`scripts/check.sh`

- [ ] **步骤 1：创建脚本**

写入：

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found: $PYTHON_BIN" >&2
  echo "Create the venv first: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 127
fi

cd "$ROOT_DIR"

echo "== unittest =="
"$PYTHON_BIN" -m unittest discover -s tests -v

echo "== compileall =="
"$PYTHON_BIN" -m compileall bot scripts tests

echo "== ok =="
```

- [ ] **步骤 2：赋予执行权限**

运行：

```bash
chmod +x scripts/check.sh
```

预期：`scripts/check.sh` 可执行。

- [ ] **步骤 3：运行脚本验证通过**

运行：

```bash
scripts/check.sh
```

预期：

```text
== unittest ==
...
Ran 75 tests
OK
== compileall ==
...
== ok ==
```

- [ ] **步骤 4：用环境变量验证脚本可切换 Python**

运行：

```bash
PYTHON_BIN=.venv/bin/python scripts/check.sh
```

预期：同样通过，并打印 `== ok ==`。

- [ ] **步骤 5：Commit**

```bash
git add scripts/check.sh
git commit -m "chore: add offline check script"
```

## 任务 3：新增 STATUS.md 作为短状态落点

**文件：**
- 创建：`STATUS.md`

- [ ] **步骤 1：创建状态文件**

写入：

```markdown
# STATUS

## Current

- M0-M6 已实现并线上运行。
- 当前版本：`1.0`，来源 `bot/version.py`。
- AI 辅助首发和只读查询增强已实现，AI 不参与审批、发组、撤组、改金额或发放标记。
- ZvZ 战报聚合/卡片模块已有单测，自动推送尚未接入。
- M7 出勤快照后置，等待真实用户反馈考勤口径。

## Harness

- 项目入口：`AGENTS.md`
- 长上下文事实：`notepad.md` 的 `## Priority Context`
- 操作文档：`README.md`、`使用说明书.md`
- 离线门禁：`scripts/check.sh`

## Next

1. 继续 KOOK 端活测和 AI 只读查询打磨。
2. 等真实用户反馈后再决定 M7 出勤口径。
3. 自动战报推送按 `docs/superpowers/specs/2026-06-14-battle-report-design.md` 另立任务接入。

## Verification

- 2026-06-15：`.venv/bin/python -m unittest discover -s tests -v` 通过，75 个测试。
- 2026-06-15：`.venv/bin/python -m compileall bot scripts tests` 通过。

## Operational Notes

- 本地和线上不得同时使用同一个 `KOOK_TOKEN` 运行 bot。
- 本地 `.env` 若使用线上旧 token，服务器 `albion-kook.service` 必须保持停止。
- 升级服务器代码时不要替换服务器上的旧 `KOOK_TOKEN`。
- `.env`、数据库、日志和备份目录不得提交。
```

- [ ] **步骤 2：检查状态文件**

运行：

```bash
sed -n '1,220p' STATUS.md
```

预期：文件只包含短状态、入口、下一步和验证证据；没有密钥、频道真实敏感内容或数据库记录明细。

- [ ] **步骤 3：Commit**

```bash
git add STATUS.md
git commit -m "docs: add project status truth file"
```

## 任务 4：更新 README 的 harness 入口和验证命令

**文件：**
- 修改：`README.md`

- [ ] **步骤 1：在“当前状态”列表追加 harness 状态**

在“当前状态”列表末尾追加：

```markdown
- 项目采用轻量 harness：接手入口见 `AGENTS.md`，短状态见 `STATUS.md`，离线门禁见 `scripts/check.sh`。
```

- [ ] **步骤 2：替换“测试”章节命令**

将“测试”章节改为：

````markdown
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
````

- [ ] **步骤 3：检查 README 片段**

运行：

```bash
rg -n "轻量 harness|scripts/check.sh|这只是离线门禁" README.md
```

预期：三处关键词都能搜到。

- [ ] **步骤 4：Commit**

```bash
git add README.md
git commit -m "docs: document harness validation entry"
```

## 任务 5：更新 notepad Priority Context

**文件：**
- 修改：`notepad.md`

- [ ] **步骤 1：在 `## Priority Context` 的当前进度附近加入 harness 事实**

追加一条 bullet：

```markdown
- 项目已采用轻量 harness：后续接手先读 `AGENTS.md` 和 `STATUS.md`；离线门禁统一跑 `scripts/check.sh`。离线通过不等于 KOOK 真实交互已活测，涉及线上/真实 bot 的结论必须补充活测证据。
```

- [ ] **步骤 2：检查 notepad 入口**

运行：

```bash
sed -n '/^## Priority Context/,+35p' notepad.md
```

预期：能看到新增 harness bullet，且未改变已有 token、服务器、M0-M7 等事实。

- [ ] **步骤 3：Commit**

```bash
git add notepad.md
git commit -m "docs: record harness handoff context"
```

## 任务 6：最终验证和差异审查

**文件：**
- 验证：`AGENTS.md`
- 验证：`scripts/check.sh`
- 验证：`STATUS.md`
- 验证：`README.md`
- 验证：`notepad.md`

- [ ] **步骤 1：运行统一离线门禁**

运行：

```bash
scripts/check.sh
```

预期：75 个测试通过，`compileall` 通过，最终打印 `== ok ==`。

- [ ] **步骤 2：确认没有提交密钥文件**

运行：

```bash
git status --short
git ls-files .env data logs bot.log
```

预期：

```text
```

`git status --short` 可显示尚未提交的业务改动，但本任务新增/修改的 harness 文件应已在前序 commits 中提交。`git ls-files .env data logs bot.log` 不应输出 `.env`、数据库或日志文件。

- [ ] **步骤 3：审查 harness diff**

运行：

```bash
git show --stat --oneline --decorate --max-count=5
```

预期：最近 commits 分别对应项目入口、验证脚本、状态文件、README、notepad，不包含业务代码文件。

- [ ] **步骤 4：记录最终验证到 STATUS.md**

把 `STATUS.md` 的 `## Verification` 更新为最新运行结果。例如：

```markdown
- 2026-06-15：`scripts/check.sh` 通过，75 个单元测试通过，`compileall bot scripts tests` 通过。
```

- [ ] **步骤 5：Commit**

```bash
git add STATUS.md
git commit -m "docs: record harness verification"
```

## 自检

- 规格覆盖度：计划覆盖接手入口、统一验证、状态落点、README/notepad truth-file 同步、安全 token 边界和最终验证。
- 占位符扫描：计划不包含禁止使用的占位步骤。
- 类型一致性：所有命令都使用本项目已有 `.venv/bin/python`、`unittest`、`compileall`、`scripts/`、`docs/superpowers/` 路径。
- 范围控制：不重构业务代码，不启动 bot，不触碰 `.env`、数据库、日志或线上 systemd。
