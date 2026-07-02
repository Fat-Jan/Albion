# AI 助手不触发 — Codex 修复计划

> 问题3：`/助手` 命令和 @机器人 提及有时无响应
> 文档基于代码分析结论，落地由 Codex 完成

---

## 根因（已确认）

### 路径 A：频道作用域拦截（最可能）

`bot/commands/ai.py` 的 mention handler：

```python
@bot.on_message()
async def on_mention(msg: Message):
    if not _message_mentions_bot(msg, bot_id):
        return
    if not region_scope.should_process_message(msg, region_cfg):
        return          # ← 静默丢弃
    ...
```

`region_scope.should_process_message()` 调用 `channel_allowed()`，检查：

```python
def channel_allowed(channel, region):
    if has_known_region_prefix(channel.name):
        return channel.name.startswith(f"{region}-")
    return channel.id in cfg.allowed_channel_ids
```

**触发条件**：频道名不带区服前缀（`eu-`/`asia-`）且频道 id 不在 `allowed_channel_ids` 列表中 → 返回 `False` → 消息被丢弃，无任何日志。

### 路径 B：bot_id 解析失败

```python
bot_id = config.token_runtime_info(region_cfg.kook_token)["bot_id"]
```

若 `token_runtime_info()` 返回 `{"bot_id": "unknown"}`，则 `_message_mentions_bot()` 永远不匹配。

### 路径 C：AI 功能未启用

`config.py`：

```python
AI_ENABLED = _bool_env("AI_ENABLED", False)   # 默认 False
```

若 OpenDeploy 环境变量 `AI_ENABLED` 未设置为 `true`，所有 AI 调用直接跳过。

---

## 线上日志验证步骤（优先执行）

在 OpenDeploy 控制台查看 bot 日志，搜索以下关键词：

```
# 确认 AI 功能是否启用
grep "AI_ENABLED\|ai_enabled"

# 确认频道过滤是否触发（需先在 region_scope.py 加日志，见下）
grep "region_scope\|channel_allowed\|should_process"

# 确认 bot_id 是否正常
grep "bot_id\|token_runtime_info"

# 确认 AI 调用是否发出
grep "AIService\|complete\|ai_complete"
```

---

## 修复任务

### 任务 1：确认并设置环境变量（操作者：运营）

在 OpenDeploy 项目 `32e65f76` → 服务 `cd6868e9` → 环境变量中确认：

| 变量 | 期望值 |
|------|--------|
| `AI_ENABLED` | `true` |
| `AI_API_KEY` | 有效的 SenseNova API Key |

若未设置，补充后重启服务即可，无需代码改动。

### 任务 2：扩大频道作用域（代码改动）

**文件**：`bot/region_scope.py`

**当前逻辑**：没有区服前缀的频道必须明确登记在 `allowed_channel_ids` 才被放行。

**改法**：增加一个 AI 专用宽松模式——当消息是对机器人的直接 mention（而不是通用消息），可以不过作用域检查，因为 @机器人 本身已经是意图明确的定向请求。

在 `bot/commands/ai.py` 的 mention handler 中移除频道过滤：

```python
# 改前：
@bot.on_message()
async def on_mention(msg: Message):
    if not _message_mentions_bot(msg, bot_id):
        return
    if not region_scope.should_process_message(msg, region_cfg):
        return
    await _handle_ai_query(msg, ai_service, region_cfg)

# 改后：
@bot.on_message()
async def on_mention(msg: Message):
    if not _message_mentions_bot(msg, bot_id):
        return
    # @机器人 是定向请求，不需要区服频道前缀过滤
    # 仍然拒绝属于另一个区服的频道（防止串区），但允许通用频道
    if region_scope.is_other_region_channel(msg.channel, region_cfg):
        return
    await _handle_ai_query(msg, ai_service, region_cfg)
```

同时在 `bot/region_scope.py` 增加 `is_other_region_channel()`：

```python
def is_other_region_channel(channel, cfg) -> bool:
    """
    True if the channel clearly belongs to the OTHER region.
    Generic channels (no region prefix, not in any list) → False (allow).
    """
    other_region = "asia" if cfg.region == "eu" else "eu"
    return channel.name.startswith(f"{other_region}-")
```

### 任务 3：`/助手` 命令频道过滤（同上逻辑）

检查 `bot/commands/ai.py` 中 `/助手` 命令注册处是否也有 `should_process_message` 检查，若有，同样替换为 `is_other_region_channel` 检查。

### 任务 4：增加日志（便于后续排查）

在 `bot/commands/ai.py` 的 mention handler 入口加一行 debug 日志：

```python
import logging
logger = logging.getLogger(__name__)

@bot.on_message()
async def on_mention(msg: Message):
    if not _message_mentions_bot(msg, bot_id):
        return
    logger.debug("AI mention received: channel=%s guild=%s",
                 getattr(msg.channel, 'name', '?'),
                 getattr(msg.ctx, 'guild_id', '?'))
    ...
```

---

## 验收标准

| 场景 | 期望结果 |
|------|----------|
| 在无 `eu-` / `asia-` 前缀的普通频道 @EU 机器人 | 机器人响应 AI 回复 |
| 在 `eu-xxx` 频道 @EU 机器人 | 机器人响应 AI 回复 |
| 在 `asia-xxx` 频道 @EU 机器人 | 机器人不响应（另一区服频道） |
| `/助手 xxx` 命令在通用频道 | 机器人响应 AI 回复 |
| `AI_ENABLED=false` 时 @机器人 | 静默不响应（功能未开启，符合预期） |

---

## 不在本次范围内

- AI 路由逻辑（`ai/router.py` 关键词匹配）的调整
- SenseNova API 超时优化（若响应慢，可将 `AI_TIMEOUT_SEC` 从默认 20s 改为 35s，在环境变量中配置）
