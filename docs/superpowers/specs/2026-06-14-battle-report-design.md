# ZvZ 战报推送设计

日期：2026-06-14

## 背景

当前机器人已经有死亡播报和手动 `/战役` 查询。死亡播报关注单条击杀/阵亡事件；`/战役` 关注用户主动查询最近战役。新增战报推送要解决的是：当绑定公会参与大型 ZvZ 战役时，自动向独立频道推送一张聚合战报，便于成员在战后快速看到本会参与情况。

已创建 KOOK 文本频道：

- 服务器：`4676167053713576`
- 频道名：`📯丨战报推送`
- 频道 ID：`8139656704033247`

## 第一版范围

只推送当前 KOOK 服务器绑定公会参与的大型战役。

不推送全服大型战役情报，不做多频道分类，不做完整复盘网页，不把战报和出勤统计合并。出勤后续可以复用战役 ID 和官方 `battle_events` 另做。

## 成功标准

- 管理员可以配置独立战报频道。
- 未配置战报频道时，定时任务不请求 AlbionBB。
- 只在北京时间 `14:30` 到次日 `05:00` 之间轮询。
- 轮询间隔为 15 分钟。
- 只推送 AlbionBB 聚合结果中包含当前绑定公会的战役。
- 同一 KOOK 服务器的同一战役只推一次，重启后仍不重复。
- AlbionBB 或 KOOK 发送失败只记录 warning，不影响死亡播报、退会复查和价格参考刷新。

## 数据源

主源使用 AlbionBB：

```text
GET https://api.albionbb.com/asia/battles?minPlayers=<阈值>&page=1
```

返回字段已实测可用：

- `albionId`
- `startedAt`
- `totalFame`
- `totalKills`
- `totalPlayers`
- `guilds[]`：`name`、`alliance`、`killFame`
- `alliances[]`：`name`、`killFame`

AlbionBB 可服务端直连，比官方 `/battles?guildId=` 更适合第一版自动聚合。官方 GameInfo 保留为后续补充详情来源，例如需要完整击杀事件、装备和出勤时再查：

```text
GET https://gameinfo-sgp.albiononline.com/api/gameinfo/events/battle/{battle_id}
```

## 配置

在 `guild_binding` 增加两个设置：

- `battle_report_channel_id TEXT`
- `battle_report_min_players INTEGER DEFAULT 50`

新增管理命令：

```text
/设置 战报频道 #频道
/设置 战报最小人数 50
```

默认最小人数为 `50`。频道未设置时任务直接跳过，不请求外部接口。

## 去重表

新增持久去重表：

```sql
CREATE TABLE IF NOT EXISTS battle_report_seen (
  kook_guild_id TEXT NOT NULL,
  battle_id     TEXT NOT NULL,
  reported_at   TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (kook_guild_id, battle_id)
);
```

发送成功后写入 seen。发送失败不写入，下一轮允许重试。

## 模块边界

`bot/albion/battle_report.py`

- 调用 `AlbionClient.albionbb_get("/battles", params={...})`
- 归一化 AlbionBB 字段
- 按绑定公会名匹配 `guilds[].name`
- 输出战报候选对象

`bot/cards/battle_report_cards.py`

- 构造 KOOK 卡片
- 展示开始时间、总人数、击杀数、总声望、本会 killFame、Top 公会和 Top 联盟
- 提供 AlbionBB 链接：`https://east.albionbb.com/battles/{battle_id}`

`bot/tasks/auto.py`

- 新增 `battle_report` 定时任务
- 15 分钟触发一次
- 北京时间不在 `14:30` 到次日 `05:00` 时直接返回
- 遍历已配置 `battle_report_channel_id` 的公会绑定
- 拉取 AlbionBB、过滤本会、查 seen、发送、写入 seen

`bot/store/db.py` 和 `bot/store/repo.py`

- 轻量迁移新增配置列
- 新增 seen 表
- 新增 `has_seen_battle_report`、`mark_battle_report_seen`

`bot/commands/admin.py`

- 新增 `/设置 战报频道`
- 新增 `/设置 战报最小人数`
- 更新设置帮助文案

## 时间窗

按北京时间判断：

- 开始：`14:30`
- 结束：次日 `05:00`

判断规则：

```text
current_time >= 14:30 or current_time < 05:00
```

这样覆盖跨午夜窗口。窗口外任务可以被 APScheduler 触发，但不请求 AlbionBB。

## 推送内容

战报卡片标题：

```text
Mika 参与大型战役
```

主体信息：

- 北京开始时间
- 总人数
- 总击杀
- 总声望
- 本会 killFame
- Top 3 公会：名称、联盟、killFame
- Top 3 联盟：名称、killFame

按钮：

- 查看 AlbionBB 战报

AlbionBB 链接格式已用 live probe 确认：`https://east.albionbb.com/battles/{battle_id}` 返回 200。

## 错误处理

- AlbionBB 请求失败：记录 warning，跳过本轮。
- 单个频道发送失败：记录 warning，不写 seen，下一轮重试。
- 战役字段缺失：尽量降级展示，缺少 `albionId` 的记录跳过。
- 公会名匹配失败：不推送，不报错。
- 多个 KOOK 服务器绑定同一 Albion 公会时，各自独立去重和推送。

## 测试计划

- 时间窗：`14:29` 不轮询，`14:30` 轮询，`23:59` 轮询，`04:59` 轮询，`05:00` 不轮询。
- 配置：未配置战报频道时不请求 AlbionBB。
- 过滤：只保留 `guilds[].name` 命中绑定公会名的战役。
- 去重：seen 表命中时不重复发送；发送成功后写 seen；发送失败不写 seen。
- 卡片：包含开始时间、总人数、击杀数、总声望、本会 killFame。
- 异常：AlbionBB 抛错不影响任务函数返回。

## 实施顺序

1. 新增 DB 列和 seen 表，补 repo 方法。
2. 新增 AlbionBB 战报聚合模块和单元测试。
3. 新增战报卡片和卡片测试。
4. 新增管理设置命令。
5. 接入 `auto.py` 定时任务。
6. 更新 README、使用说明书、notepad。
7. 运行测试、编译、live probe，并重启 bot。
