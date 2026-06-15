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
- 当前线上服务和调试状态以 `STATUS.md` 与 `notepad.md` 为准。

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
