const endpoints = {
  status: "/api/status",
  invites: "/api/invites",
  events: "/api/events/high-fame?limit=20",
  leaderboards: "/api/leaderboards?limit=20",
  gold: "/api/market/gold?limit=8",
  attendance: "/api/attendance/recent?limit=20&min_guild_players=20",
};

document.getElementById("refresh-button").addEventListener("click", () => {
  loadDashboard();
});

loadDashboard();

async function loadDashboard() {
  setLoading(true);
  renderNotice([]);
  try {
    const results = await Promise.allSettled(
      Object.entries(endpoints).map(async ([key, url]) => {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`${key}: ${response.status} ${response.statusText}`);
        }
        return [key, await response.json()];
      }),
    );

    const data = {};
    const errors = [];
    for (const result of results) {
      if (result.status === "fulfilled") {
        const [key, payload] = result.value;
        data[key] = payload;
      } else {
        errors.push(result.reason?.message || "Request failed");
      }
    }

    renderStatus(data.status || {});
    renderInvites(data.invites || {});
    renderCollectors((data.status || {}).collectors || []);
    renderGold((data.gold || {}).items || []);
    renderEvents((data.events || {}).items || []);
    renderLeaderboards((data.leaderboards || {}).items || []);
    renderAttendance((data.attendance || {}).items || []);
    renderOpsSummary(data, errors);
    renderNotice(errors);
  } finally {
    setLoading(false);
  }
}

function renderStatus(status) {
  const collectorSummary = status.collector_summary || summarizeCollectors(status.collectors || []);
  renderHealth(collectorSummary);
  setText("status-region", status.region || "-");
  setText("status-version", status.version || "-");
  setText("status-heartbeat", formatTime(status.last_heartbeat));
  setText("status-task", formatTime(status.last_task_run));
}

function renderOpsSummary(data, errors) {
  const status = data.status || {};
  const collectorSummary = status.collector_summary || summarizeCollectors(status.collectors || []);
  const collectors = collectorSummary.total
    ? `${collectorSummary.ok || 0}/${collectorSummary.total} ok`
    : "waiting";

  const events = ((data.events || {}).items || []).length;
  const leaderboardSnapshots = ((data.leaderboards || {}).items || []);
  const leaderboardKinds = new Set(
    leaderboardSnapshots.map((snapshot) => snapshot.kind).filter(Boolean),
  ).size || leaderboardSnapshots.length;
  const goldRows = ((((data.gold || {}).items || [])[0] || {}).items || []).length;
  const signals = errors.length
    ? `${errors.length} panel errors`
    : `${events} ev / ${leaderboardKinds} bd / ${goldRows} gold`;

  const guildNames = ((data.attendance || {}).items || [])
    .map((item) => item.albion_guild_name || item.albion_guild_id)
    .filter(Boolean);

  setText("summary-collectors", collectors);
  setText("summary-signals", signals);
  setText("summary-guilds", guildNames.length ? shortList(guildNames) : "waiting");
}

function renderHealth(summary) {
  const card = document.getElementById("status-health-card");
  const pill = document.getElementById("status-health");
  const note = document.getElementById("status-health-note");
  const state = summary.status || "idle";
  card.className = `is-${state}`;
  pill.className = `pill ${statusClass(state)}`;
  pill.textContent = healthLabel(state);
  note.textContent = `${summary.ok || 0} ok / ${summary.warn || 0} warn / ${summary.bad || 0} bad`;
}

function renderInvites(invites) {
  const root = document.getElementById("invite-actions");
  clear(root);
  addInvite(root, "Add EU Bot", invites.eu, "button");
  addInvite(root, "Add ASIA Bot", invites.asia, "button secondary");
}

function addInvite(root, label, href, className) {
  if (!href) {
    const disabled = document.createElement("span");
    disabled.className = "button secondary is-disabled";
    disabled.setAttribute("aria-disabled", "true");
    disabled.textContent = `${label.replace(/^Add\s+/, "")}: unset`;
    root.appendChild(disabled);
    return;
  }
  const link = document.createElement("a");
  link.className = className;
  link.href = href;
  link.rel = "noopener noreferrer";
  link.target = "_blank";
  link.textContent = label;
  root.appendChild(link);
}

function renderCollectors(items) {
  const root = document.getElementById("collector-rows");
  clear(root);
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty";
    cell.textContent = "No collector runs yet.";
    row.appendChild(cell);
    root.appendChild(row);
    return;
  }
  for (const item of items) {
    const row = document.createElement("tr");
    const state = statusClass(item.status);
    row.className = `collector-row is-${state || "idle"}`;
    appendCell(row, item.name || "-");
    appendCell(row, item.kook_guild_id || "-");
    appendStatusCell(row, item.status || "-");
    appendCell(row, formatTime(item.last_run_at));
    root.appendChild(row);
  }
}

function renderGold(snapshots) {
  const root = document.getElementById("gold-list");
  clear(root);
  const latest = snapshots[0];
  if (!latest || !(latest.items || []).length) {
    empty(root, "No gold snapshot yet.");
    return;
  }
  for (const row of latest.items.slice(0, 8)) {
    root.appendChild(summaryRow(
      goldPrice(row),
      row.timestamp || row.Timestamp || latest.captured_at,
      latest.captured_at,
    ));
  }
}

function renderEvents(items) {
  const root = document.getElementById("event-list");
  clear(root);
  if (!items.length) {
    empty(root, "No high-fame events cached.");
    return;
  }
  for (const item of items.slice(0, 10)) {
    const killer = item.killer || {};
    const victim = item.victim || {};
    root.appendChild(summaryRow(
      `${killer.name || "Unknown"} -> ${victim.name || "Unknown"}`,
      `${formatNumber(item.fame)} fame`,
      formatTime(item.event_time),
    ));
  }
}

function renderLeaderboards(snapshots) {
  const root = document.getElementById("leaderboard-list");
  clear(root);
  if (!snapshots.length) {
    empty(root, "No leaderboard snapshots yet.");
    return;
  }
  const latestByKind = new Map();
  for (const snapshot of snapshots) {
    if (!latestByKind.has(snapshot.kind)) {
      latestByKind.set(snapshot.kind, snapshot);
    }
  }
  for (const snapshot of latestByKind.values()) {
    const group = document.createElement("section");
    group.className = "leaderboard-group";
    const title = document.createElement("h3");
    title.textContent = `${labelKind(snapshot.kind)} - ${formatTime(snapshot.captured_at)}`;
    group.appendChild(title);

    const list = document.createElement("ol");
    for (const item of (snapshot.items || []).slice(0, 5)) {
      const li = document.createElement("li");
      li.textContent = leaderboardLine(item);
      list.appendChild(li);
    }
    if (!list.childNodes.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "Empty snapshot.";
      list.appendChild(li);
    }
    group.appendChild(list);
    root.appendChild(group);
  }
}

function renderAttendance(items) {
  const root = document.getElementById("attendance-list");
  clear(root);
  if (!items.length) {
    empty(root, "No attendance snapshot yet.");
    return;
  }
  for (const item of items) {
    const snapshot = item.snapshot || {};
    const members = (snapshot.members || []).slice(0, 6);
    const memberDetail = members
      .map((member) => `${member.name || member.Name}: ${member.participated_battles || 0}`)
      .join(" | ");
    const recentBattles = (snapshot.battles || []).slice(0, 3);
    const battleDetail = recentBattles.length
      ? `Recent battles: ${recentBattles.map(battleLine).join(" / ")}`
      : "";
    const detail = [memberDetail || "No member rows.", battleDetail]
      .filter(Boolean)
      .join(" | ");
    root.appendChild(summaryRow(
      item.albion_guild_name || item.albion_guild_id || "Guild",
      detail,
      `${snapshot.counted_battle_count || 0}/${snapshot.battle_count || 0} battles`,
    ));
  }
}

function summaryRow(title, meta, badge) {
  const row = document.createElement("div");
  row.className = "row";
  const body = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title || "-";
  const small = document.createElement("p");
  small.className = "meta";
  small.textContent = meta || "-";
  body.append(strong, small);

  const pill = document.createElement("span");
  pill.className = "pill";
  pill.textContent = badge || "-";
  row.append(body, pill);
  return row;
}

function leaderboardLine(item) {
  const name = item.Name || item.name || item.PlayerName || item.GuildName || "Unknown";
  const fame = item.Fame || item.fame || item.KillFame || item.TotalFame || item.Value || "";
  return fame ? `${name} - ${formatNumber(fame)}` : name;
}

function battleLine(item) {
  const when = formatTime(item.start_time || item.startTime);
  const players = item.guild_players ?? item.guildPlayers ?? "-";
  return `${when} (${players} guild)`;
}

function labelKind(kind) {
  return String(kind || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortList(items) {
  const unique = [...new Set(items)];
  if (unique.length <= 2) {
    return unique.join(", ");
  }
  return `${unique.slice(0, 2).join(", ")} +${unique.length - 2}`;
}

function goldPrice(row) {
  const value = row.price || row.Price || row.value || row.Value || "";
  return value ? formatNumber(value) : "No price";
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function formatNumber(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) {
    return String(value || 0);
  }
  return number.toLocaleString();
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value || "-";
  row.appendChild(cell);
}

function appendStatusCell(row, value) {
  const cell = document.createElement("td");
  const pill = document.createElement("span");
  pill.className = `pill ${statusClass(value)}`;
  pill.textContent = value || "-";
  cell.appendChild(pill);
  row.appendChild(cell);
}

function statusClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "ok") {
    return "ok";
  }
  if (normalized === "partial" || normalized === "warn" || normalized === "idle") {
    return "warn";
  }
  if (normalized === "error" || normalized === "failed") {
    return "bad";
  }
  if (normalized === "bad") {
    return "bad";
  }
  return "";
}

function summarizeCollectors(collectors) {
  const summary = { status: "idle", total: collectors.length, ok: 0, warn: 0, bad: 0 };
  for (const collector of collectors) {
    const state = statusClass(collector.status);
    if (state === "ok") {
      summary.ok += 1;
    } else if (state === "bad") {
      summary.bad += 1;
    } else {
      summary.warn += 1;
    }
  }
  if (summary.bad) {
    summary.status = "bad";
  } else if (summary.warn) {
    summary.status = "warn";
  } else if (summary.total) {
    summary.status = "ok";
  }
  return summary;
}

function healthLabel(state) {
  if (state === "ok") {
    return "Operational";
  }
  if (state === "bad") {
    return "Attention";
  }
  if (state === "warn") {
    return "Degraded";
  }
  return "Waiting";
}

function renderNotice(errors) {
  const notice = document.getElementById("dashboard-notice");
  if (!errors.length) {
    notice.hidden = true;
    notice.textContent = "";
    return;
  }
  notice.hidden = false;
  notice.textContent = `Some panels failed to load: ${errors.join(" | ")}`;
}

function setLoading(isLoading) {
  const button = document.getElementById("refresh-button");
  const label = button.querySelector(".refresh-label");
  const shell = document.getElementById("dashboard-shell");
  document.body.classList.toggle("is-loading", isLoading);
  shell.setAttribute("aria-busy", String(isLoading));
  button.disabled = isLoading;
  button.setAttribute("aria-label", isLoading ? "Refreshing dashboard" : "Refresh dashboard");
  label.textContent = isLoading ? "Refreshing" : "Refresh";
}

function empty(root, message) {
  const node = document.createElement("p");
  node.className = "empty";
  node.textContent = message;
  root.appendChild(node);
}

function clear(node) {
  node.replaceChildren();
}

function setText(id, value) {
  document.getElementById(id).textContent = value || "-";
}
