# 前端重设计规范 — Albion KOOK Ops Dashboard

> 交付给 Codex 的落地任务文档。Claude 负责规划，Codex 负责实现。
> 文件路径：`web/index.html`、`web/styles.css`、`web/app.js`

---

## 目标

1. **中英双语**：顶部切换按钮，localStorage 记住偏好，默认中文
2. **暗色主题**：参考行业惯例（albiononline2d / murderledger），金色强调
3. **布局重组**：把5个平铺 panel 重新分区，逻辑分组清晰
4. **视觉升级**：更紧凑的数据密度，状态色规范，区分 EU/ASIA

---

## 设计原则

- 不引入任何 JS 框架或构建工具，保持纯 HTML/CSS/JS
- i18n 用一个轻量 JS 对象（见下方方案），不用任何 i18n 库
- 现有 API 端点不变（`/api/status`、`/api/events/high-fame` 等）
- 每行可追溯到用户需求，不加额外功能

---

## 色彩 Token

```css
:root {
  /* 背景层次 */
  --bg-base:    #0f1117;   /* 页面底色 */
  --bg-surface: #181c27;   /* panel 底色 */
  --bg-raised:  #1f2436;   /* hover / 次级容器 */

  /* 强调色（Albion 金）*/
  --accent:      #c9a84c;
  --accent-dim:  #8a6f2e;

  /* 文字 */
  --text-primary:   #e8e8e8;
  --text-secondary: #8b8fa8;
  --text-muted:     #545878;

  /* 状态色 */
  --ok:   #4caf7d;
  --warn: #e6a817;
  --bad:  #e05252;

  /* 边框 */
  --border: rgba(255,255,255,0.06);
}
```

---

## 页面结构（重组后）

```
┌─────────────────────────────────────────────────────────┐
│  TOPBAR                                                  │
│  [EU 标识]  Albion KOOK 运营台   [EN/中] [刷新] [邀请]   │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│  STATUS BAND                                             │
│  ● Health  |  区服 EU  |  版本 v1.x  |  心跳 ...        │
└─────────────────────────────────────────────────────────┘
┌──────────────────────────┬──────────────────────────────┐
│  PANEL: 采集器（宽）      │  PANEL: 声望事件              │
│  Name | Guild | Status   │  击杀者 → 被击者 | 声望值      │
│  Last Run                │  ...                         │
├──────────────────────────┴──────────────────────────────┤
│  PANEL: 黄金走势（半宽）   PANEL: 排行榜（半宽）          │
│  价格 | 时间              击杀 / 公会 / 声望              │
├─────────────────────────────────────────────────────────┤
│  PANEL: 出勤快照（宽）                                   │
│  公会名 | 出勤/总战役 | 成员列表                          │
└─────────────────────────────────────────────────────────┘
```

---

## i18n 方案

### 原则
- 一个 `I18N` 对象，两套字符串，key 对应 `data-i18n` 属性
- `setLang(lang)` 遍历所有 `[data-i18n]` 元素，替换 `textContent`
- 动态渲染的内容（事件行、排行榜行等）在 `renderXxx()` 函数里判断 `currentLang` 返回对应字符串

### i18n 对象结构

```js
const I18N = {
  en: {
    title:           "Ops Dashboard",
    eyebrow:         "Albion EU KOOK",
    collectors:      "Collectors",
    gold:            "Gold Price",
    highFame:        "High Fame",
    leaderboards:    "Leaderboards",
    attendance:      "Attendance",
    health:          "Health",
    region:          "Region",
    version:         "Version",
    heartbeat:       "Heartbeat",
    lastTask:        "Last Task",
    refresh:         "Refresh",
    addEuBot:        "Add EU Bot",
    addAsiaBot:      "Add ASIA Bot",
    noCollectors:    "No collector runs yet.",
    noGold:          "No gold snapshot yet.",
    noFame:          "No high-fame events cached.",
    noLeaderboard:   "No leaderboard snapshots yet.",
    noAttendance:    "No attendance snapshot yet.",
    statusOperational: "Operational",
    statusDegraded:    "Degraded",
    statusAttention:   "Attention",
    statusWaiting:     "Waiting",
    colName:         "Name",
    colGuild:        "Guild",
    colStatus:       "Status",
    colLastRun:      "Last Run",
    summaryCollectors: "Collectors",
    summarySignals:    "Signals",
    summaryGuilds:     "Guilds",
  },
  zh: {
    title:           "运营台",
    eyebrow:         "Albion EU KOOK",
    collectors:      "采集器",
    gold:            "黄金走势",
    highFame:        "高声望事件",
    leaderboards:    "排行榜",
    attendance:      "出勤快照",
    health:          "健康",
    region:          "区服",
    version:         "版本",
    heartbeat:       "心跳",
    lastTask:        "上次任务",
    refresh:         "刷新",
    addEuBot:        "添加欧服机器人",
    addAsiaBot:      "添加亚服机器人",
    noCollectors:    "暂无采集器记录",
    noGold:          "暂无黄金快照",
    noFame:          "暂无高声望事件",
    noLeaderboard:   "暂无排行榜快照",
    noAttendance:    "暂无出勤快照",
    statusOperational: "正常运行",
    statusDegraded:    "部分降级",
    statusAttention:   "需要关注",
    statusWaiting:     "等待中",
    colName:         "名称",
    colGuild:        "公会 ID",
    colStatus:       "状态",
    colLastRun:      "上次运行",
    summaryCollectors: "采集器",
    summarySignals:    "信号",
    summaryGuilds:     "公会",
  },
};

let currentLang = localStorage.getItem("lang") || "zh";

function setLang(lang) {
  currentLang = lang;
  localStorage.setItem("lang", lang);
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (I18N[lang][key]) el.textContent = I18N[lang][key];
  });
  // 重新渲染动态内容（空状态文本等）
  loadDashboard();
}

function t(key) {
  return I18N[currentLang][key] || key;
}
```

---

## HTML 修改要点

### `<html lang>` 动态化

```html
<html lang="zh-CN">
```
由 `setLang()` 在运行时更新。

### topbar 新增语言切换

在 `.actions` div 中加入：

```html
<div class="lang-switcher" role="group" aria-label="语言切换">
  <button type="button" class="lang-btn" data-lang="zh" aria-pressed="true">中</button>
  <button type="button" class="lang-btn" data-lang="en" aria-pressed="false">EN</button>
</div>
```

JS 绑定：

```js
document.querySelectorAll(".lang-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const lang = btn.dataset.lang;
    document.querySelectorAll(".lang-btn").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.lang === lang));
    });
    setLang(lang);
  });
});
```

### `data-i18n` 标注静态文本

所有静态标签加 `data-i18n` 属性。示例：

```html
<h2 data-i18n="collectors">Collectors</h2>
<th data-i18n="colName">Name</th>
<th data-i18n="colGuild">Guild</th>
<th data-i18n="colStatus">Status</th>
<th data-i18n="colLastRun">Last Run</th>
<span class="label" data-i18n="health">Health</span>
```

---

## CSS 修改要点

### 1. 应用色彩 token

把现有 CSS 中的硬编码颜色全部替换为上方 token 变量。

### 2. topbar 布局调整

```css
.topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.5rem;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}

.topbar .actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
```

### 3. 语言切换按钮

```css
.lang-switcher {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}

.lang-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.25rem 0.6rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.15s;
}

.lang-btn[aria-pressed="true"] {
  background: var(--accent);
  color: #000;
  font-weight: 600;
}
```

### 4. panel 统一卡片样式

```css
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  margin: 0;
}
```

### 5. grid 布局

```css
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding: 1rem 1.5rem;
}

.panel.wide {
  grid-column: 1 / -1;
}

@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; }
  .panel.wide { grid-column: unset; }
}
```

---

## 动态渲染函数 i18n 接入

每个 `renderXxx` 函数中的空状态文本改用 `t()` 调用：

```js
// 原来：
empty(root, "No collector runs yet.");
// 改为：
empty(root, t("noCollectors"));
```

`healthLabel()` 函数改用 `t()`：

```js
function healthLabel(state) {
  if (state === "ok")   return t("statusOperational");
  if (state === "bad")  return t("statusAttention");
  if (state === "warn") return t("statusDegraded");
  return t("statusWaiting");
}
```

`addInvite()` 中的按钮标签改用 `t()`：

```js
addInvite(root, t("addEuBot"),   invites.eu,   "button");
addInvite(root, t("addAsiaBot"), invites.asia, "button secondary");
```

---

## 验收标准

| 项目 | 验证方式 |
|------|----------|
| 点击「中/EN」切换，所有静态文本实时变更 | 手动检查 |
| localStorage 记住语言偏好，刷新后保留 | 手动：设置 EN，F5，确认仍为 EN |
| 默认语言为中文（新用户/清 storage） | 清 localStorage 后刷新 |
| 暗色主题，主色 #0f1117，强调色 #c9a84c | DevTools 核查 CSS 变量 |
| 采集器、排行榜使用 `.wide` 撑满两列 | 视觉检查 |
| 移动端（宽 < 768px）退化为单列 | 缩窄窗口 |
| 现有 API 端点和数据渲染逻辑不改 | `loadDashboard()` 返回正常数据 |

---

## 不在本次范围内

- ASIA bot 独立 tab / 双 bot 切换（留给后续迭代）
- 后端 i18n API 翻译（仅前端文案切换）
- 新增 API 端点或数据字段
