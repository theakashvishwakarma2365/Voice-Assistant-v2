const apiBase = "/api";

// ═══════════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════════
let sheets = [];
let cachedTasks = [];
let cachedMeetings = [];
let systemStatus = {};
let selectedSheetId = null;
let chatHistory = [];
let typingTimer = null;
let fallbackHomeTimeout = null;
let currentResponseIsClarification = false;
let currentMode = "chat";
const sessionId = 'session_' + Math.random().toString(36).substring(2, 15);

let ws = null;
let wsConnecting = false;
let audioContext = null;
let processor = null;
let analyser = null;
let dataArray = null;
let animationId = null;
let stream = null;
let isRecording = false;
let activeAudio = null;

let currentPomodoro = null;
let pomodoroInterval = null;

const ScreenState = {
  activeScreen: "home",
  activeItemIndex: 0,
  faceState: "idle",
  selectedTask: null,
  assistantBubbleText: "",
  menuItems: [
    { label: "✅ Tasks", value: "tasks" },
    { label: "📅 Meetings", value: "meetings" },
    { label: "📁 Sheets", value: "sheets" },
    { label: "📝 Notes", value: "notes" },
    { label: "⏱ Pomodoro", value: "pomodoro" },
    { label: "🔔 Reminders", value: "reminders" },
    { label: "⚙️ Settings", value: "settings" },
    { label: "📶 WiFi", value: "wifi" }
  ],
  wifiNetworks: [
    { name: "📶 HomeNetwork_5G", strength: "████" },
    { name: "📶 Office_WiFi", strength: "███░" },
  ],
  settingsItems: [
    { label: "🔊 Beep: ON", key: "beeps", value: true },
    { label: "🔄 Force Sync", key: "sync" },
    { label: "🧹 Clear Cache", key: "clearCache" },
    { label: "ℹ️ System Info", key: "sysInfo" }
  ]
};

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════
async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const errorText = await res.text();
    try { const d = JSON.parse(errorText); throw new Error(d.detail || d.error || errorText || res.statusText); }
    catch (e) { if (e.message !== errorText) throw e; throw new Error(errorText || res.statusText); }
  }
  return res.json();
}

function log(message) {
  const log = document.getElementById("activity-log");
  if (!log) return;
  const entry = document.createElement("p");
  entry.textContent = `${new Date().toLocaleTimeString()} | ${message}`;
  log.prepend(entry);
}

function playBeep(type = "click") {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    if (type === "click") {
      osc.type = "sine"; osc.frequency.setValueAtTime(1200, ctx.currentTime);
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.05);
      osc.start(); osc.stop(ctx.currentTime + 0.05);
    } else if (type === "success") {
      osc.type = "sine"; osc.frequency.setValueAtTime(900, ctx.currentTime);
      osc.frequency.setValueAtTime(1400, ctx.currentTime + 0.07);
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);
      osc.start(); osc.stop(ctx.currentTime + 0.2);
    } else if (type === "error") {
      osc.type = "triangle"; osc.frequency.setValueAtTime(150, ctx.currentTime);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.start(); osc.stop(ctx.currentTime + 0.25);
    }
  } catch (e) {}
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODE MANAGEMENT
// ═══════════════════════════════════════════════════════════════════════════════
const MODE_ICONS = { chat: "💬", focus: "🎯", briefing: "📋", research: "🔬", dnd: "🔕" };
const MODE_LABELS = { chat: "CHAT", focus: "FOCUS", briefing: "BRIEFING", research: "RESEARCH", dnd: "DND" };

function updateModeUI(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-pill").forEach(p => {
    p.classList.toggle("active", p.dataset.mode === mode);
  });
  const badge = document.getElementById("mode-badge");
  if (badge) badge.textContent = `${MODE_ICONS[mode] || "💬"} ${MODE_LABELS[mode] || mode.toUpperCase()}`;
  const nameEl = document.getElementById("settings-mode-name");
  if (nameEl) nameEl.textContent = mode;
}

async function setMode(mode) {
  try {
    await fetchJson(`${apiBase}/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, session_id: sessionId }),
    });
    updateModeUI(mode);
    log(`Mode switched to: ${mode.toUpperCase()}`);
  } catch (err) {
    log(`Mode switch failed: ${err.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PANEL NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════════
function switchPanel(panelId) {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  const panel = document.getElementById(`panel-${panelId}`);
  if (panel) panel.classList.add("active");
  const btn = document.querySelector(`.nav-btn[data-panel="${panelId}"]`);
  if (btn) btn.classList.add("active");

  if (panelId === "tasks") loadTasks();
  if (panelId === "notes") loadNotes();
  if (panelId === "meetings") loadMeetings();
  if (panelId === "reminders") loadReminders();
  if (panelId === "pomodoro") { loadActivePomodoro(); loadPomodoroHistory(); }
  if (panelId === "settings") loadStatus();
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS
// ═══════════════════════════════════════════════════════════════════════════════
async function loadStatus() {
  try {
    const s = await fetchJson(`${apiBase}/status`);
    systemStatus = s;
    const fmtBool = (v) => v ? "✓ On" : "✗ Off";
    const uptime = s.uptime_seconds > 3600
      ? `${Math.floor(s.uptime_seconds/3600)}h ${Math.floor((s.uptime_seconds%3600)/60)}m`
      : `${Math.round(s.uptime_seconds)}s`;
    ["status-uptime", "settings-uptime"].forEach(id => {
      const el = document.getElementById(id); if (el) el.textContent = uptime;
    });
    ["status-whisper", "settings-whisper"].forEach(id => {
      const el = document.getElementById(id); if (el) el.textContent = fmtBool(s.whisper_loaded);
    });
    ["status-ollama", "settings-ollama"].forEach(id => {
      const el = document.getElementById(id); if (el) el.textContent = fmtBool(s.ollama_reachable);
    });
    ["status-sheets", "settings-sheets"].forEach(id => {
      const el = document.getElementById(id); if (el) el.textContent = fmtBool(s.sheets_connected);
    });
    const remEl = document.getElementById("status-reminders"); if (remEl) remEl.textContent = s.pending_reminders;
    const cacheEl = document.getElementById("status-cache"); if (cacheEl) cacheEl.textContent = `${s.audio_cache_mb} MB`;
  } catch (err) { log(`Status fetch failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHEETS
// ═══════════════════════════════════════════════════════════════════════════════
async function loadSheets() {
  try {
    sheets = await fetchJson(`${apiBase}/sheets`);
    const sel = document.getElementById("sheet-select");
    if (sel) {
      sel.innerHTML = "";
      sheets.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id; opt.textContent = s.name;
        sel.appendChild(opt);
      });
      if (!selectedSheetId && sheets.length) selectedSheetId = sheets[0].id;
      if (selectedSheetId) sel.value = selectedSheetId;
    }
  } catch (err) { log(`Sheets fetch failed: ${err.message}`); }
}

async function createSheet() {
  const nameEl = document.getElementById("new-sheet-name");
  const colsEl = document.getElementById("new-sheet-columns");
  const name = nameEl?.value.trim();
  if (!name) return;
  const custom_columns = colsEl?.value.trim()
    ? colsEl.value.split(",").map(c => c.trim()).filter(Boolean)
    : undefined;
  try {
    const sheet = await fetchJson(`${apiBase}/sheets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, custom_columns }),
    });
    if (nameEl) nameEl.value = "";
    if (colsEl) colsEl.value = "";
    playBeep("success");
    log(`Sheet created: "${name}"`);
    selectedSheetId = sheet.id;
    await loadSheets();
    await loadTasks();
  } catch (err) { playBeep("error"); log(`Sheet create failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// TASKS
// ═══════════════════════════════════════════════════════════════════════════════
function renderTasks(tasks) {
  const list = document.getElementById("task-list");
  if (!list) return;
  list.innerHTML = "";
  if (!tasks.length) { list.innerHTML = '<p class="empty-state">No tasks found.</p>'; return; }
  tasks.forEach(task => {
    const card = document.createElement("div");
    card.className = "task-card";
    card.innerHTML = `
      <div class="task-details">
        <p class="task-title">${escHtml(task.title)}</p>
        <div class="task-meta">
          <span class="tag ${task.status}">${task.status.toUpperCase()}</span>
          <span class="tag ${task.priority}">${task.priority.toUpperCase()}</span>
          ${task.due_date ? `<span>📅 ${new Date(task.due_date).toLocaleDateString()}</span>` : ""}
        </div>
      </div>
      <div class="task-actions">
        <button class="icon-btn task-done-btn" data-id="${task.id}" data-status="${task.status}" title="Toggle done">${task.status === "done" ? "↩" : "✓"}</button>
        <button class="delete-btn task-del-btn" data-id="${task.id}" title="Delete">✕</button>
      </div>
    `;
    list.appendChild(card);
  });
  list.querySelectorAll(".task-done-btn").forEach(btn => btn.addEventListener("click", async () => {
    const id = btn.dataset.id;
    const newStatus = btn.dataset.status === "done" ? "pending" : "done";
    try {
      await fetchJson(`${apiBase}/tasks/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: newStatus }) });
      playBeep("success"); await loadTasks();
    } catch (err) { playBeep("error"); log(`Task update failed: ${err.message}`); }
  }));
  list.querySelectorAll(".task-del-btn").forEach(btn => btn.addEventListener("click", async () => {
    try {
      await fetch(`${apiBase}/tasks/${btn.dataset.id}`, { method: "DELETE" });
      playBeep("success"); log("Task deleted."); await loadTasks();
    } catch (err) { playBeep("error"); log(`Task delete failed: ${err.message}`); }
  }));
}

async function loadTasks() {
  if (!selectedSheetId) { renderTasks([]); return; }
  const statusEl = document.getElementById("task-status-filter");
  const status = statusEl?.value || "";
  const params = new URLSearchParams();
  params.set("sheet_id", selectedSheetId);
  if (status) params.set("status", status);
  try {
    const tasks = await fetchJson(`${apiBase}/tasks?${params}`);
    cachedTasks = tasks;
    renderTasks(tasks);
    renderScreen();
  } catch (err) { log(`Tasks fetch failed: ${err.message}`); }
}

async function createTask() {
  if (!selectedSheetId) { log("Select a sheet first."); return; }
  const title = document.getElementById("task-title")?.value.trim();
  if (!title) return;
  const due_date = document.getElementById("task-due-date")?.value || null;
  const priority = document.getElementById("task-priority")?.value || "normal";
  try {
    await fetchJson(`${apiBase}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet_id: Number(selectedSheetId), title, due_date, priority }),
    });
    document.getElementById("task-title").value = "";
    document.getElementById("task-due-date").value = "";
    playBeep("success"); log(`Task added: "${title}"`); await loadTasks();
  } catch (err) { playBeep("error"); log(`Task create failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// NOTES
// ═══════════════════════════════════════════════════════════════════════════════
let editingNoteId = null;

function renderNotes(notes) {
  const list = document.getElementById("note-list");
  if (!list) return;
  list.innerHTML = "";
  if (!notes.length) { list.innerHTML = '<p class="empty-state">No notes yet.</p>'; return; }
  notes.forEach(note => {
    const card = document.createElement("div");
    card.className = "note-card";
    const tags = (note.tags || []).map(t => `<span class="note-tag">${escHtml(t)}</span>`).join("");
    card.innerHTML = `
      <div class="note-card-header">
        <span class="note-card-title">${escHtml(note.title)}</span>
        <span class="note-card-date">${new Date(note.created_at).toLocaleDateString()}</span>
      </div>
      ${tags ? `<div class="note-tags">${tags}</div>` : ""}
      <p class="note-card-preview">${escHtml((note.content || "").slice(0, 120))}${(note.content || "").length > 120 ? "…" : ""}</p>
      <div class="note-card-actions">
        <button class="icon-btn note-edit-btn" data-id="${note.id}">✏️ Edit</button>
        <button class="delete-btn note-del-btn" data-id="${note.id}">✕</button>
      </div>
    `;
    list.appendChild(card);
  });
  list.querySelectorAll(".note-edit-btn").forEach(btn => btn.addEventListener("click", async () => {
    try {
      const note = await fetchJson(`${apiBase}/notes/${btn.dataset.id}`);
      document.getElementById("note-editor-title").value = note.title;
      document.getElementById("note-editor-content").value = note.content || "";
      document.getElementById("note-editor-tags").value = (note.tags || []).join(", ");
      document.getElementById("note-editor-id").value = note.id;
      editingNoteId = note.id;
      document.getElementById("note-save-btn").textContent = "Update";
    } catch (err) { log(`Note load failed: ${err.message}`); }
  }));
  list.querySelectorAll(".note-del-btn").forEach(btn => btn.addEventListener("click", async () => {
    try {
      await fetch(`${apiBase}/notes/${btn.dataset.id}`, { method: "DELETE" });
      playBeep("success"); log("Note deleted."); await loadNotes();
    } catch (err) { playBeep("error"); log(`Note delete failed: ${err.message}`); }
  }));
}

async function loadNotes() {
  const q = document.getElementById("note-search")?.value.trim() || "";
  const params = q ? `?q=${encodeURIComponent(q)}` : "";
  try {
    const notes = await fetchJson(`${apiBase}/notes${params}`);
    renderNotes(notes);
  } catch (err) { log(`Notes fetch failed: ${err.message}`); }
}

async function saveNote() {
  const title = document.getElementById("note-editor-title")?.value.trim();
  const content = document.getElementById("note-editor-content")?.value.trim();
  const tagsRaw = document.getElementById("note-editor-tags")?.value.trim();
  const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];
  if (!title) { log("Note title required."); return; }
  try {
    if (editingNoteId) {
      await fetchJson(`${apiBase}/notes/${editingNoteId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content, tags }),
      });
      log(`Note updated: "${title}"`);
    } else {
      await fetchJson(`${apiBase}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, content, tags }),
      });
      log(`Note saved: "${title}"`);
    }
    playBeep("success"); clearNoteEditor(); await loadNotes();
  } catch (err) { playBeep("error"); log(`Note save failed: ${err.message}`); }
}

function clearNoteEditor() {
  document.getElementById("note-editor-title").value = "";
  document.getElementById("note-editor-content").value = "";
  document.getElementById("note-editor-tags").value = "";
  document.getElementById("note-editor-id").value = "";
  document.getElementById("note-save-btn").textContent = "Save";
  editingNoteId = null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MEETINGS
// ═══════════════════════════════════════════════════════════════════════════════
function renderMeetings(meetings) {
  const list = document.getElementById("meeting-list");
  if (!list) return;
  list.innerHTML = "";
  if (!meetings.length) { list.innerHTML = '<p class="empty-state">No meetings.</p>'; return; }
  meetings.forEach(m => {
    const card = document.createElement("div");
    card.className = "task-card";
    card.innerHTML = `
      <div class="task-details">
        <p class="task-title">${escHtml(m.title)}</p>
        <div class="task-meta">
          ${m.meeting_date ? `<span>📅 ${new Date(m.meeting_date).toLocaleString()}</span>` : ""}
          ${m.participants ? `<span>👥 ${escHtml(m.participants)}</span>` : ""}
        </div>
      </div>
      <button class="delete-btn" data-id="${m.id}">✕</button>
    `;
    list.appendChild(card);
  });
  list.querySelectorAll(".delete-btn").forEach(btn => btn.addEventListener("click", async () => {
    try {
      await fetch(`${apiBase}/meetings/${btn.dataset.id}`, { method: "DELETE" });
      playBeep("success"); await loadMeetings();
    } catch (err) { playBeep("error"); log(`Meeting delete failed: ${err.message}`); }
  }));
}

async function loadMeetings() {
  try {
    cachedMeetings = await fetchJson(`${apiBase}/meetings`);
    renderMeetings(cachedMeetings);
  } catch (err) { log(`Meetings fetch failed: ${err.message}`); }
}

async function createMeeting() {
  const title = document.getElementById("meeting-title")?.value.trim();
  if (!title) return;
  const meeting_date = document.getElementById("meeting-date")?.value || null;
  const participants = document.getElementById("meeting-participants")?.value.trim() || null;
  const sheetId = selectedSheetId || (sheets[0]?.id) || 1;
  try {
    await fetchJson(`${apiBase}/meetings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet_id: Number(sheetId), title, meeting_date, participants }),
    });
    document.getElementById("meeting-title").value = "";
    document.getElementById("meeting-date").value = "";
    document.getElementById("meeting-participants").value = "";
    playBeep("success"); log(`Meeting scheduled: "${title}"`); await loadMeetings();
  } catch (err) { playBeep("error"); log(`Meeting create failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// REMINDERS
// ═══════════════════════════════════════════════════════════════════════════════
async function loadReminders() {
  try {
    const items = await fetchJson(`${apiBase}/reminders`);
    const list = document.getElementById("reminder-list");
    if (!list) return;
    list.innerHTML = "";
    if (!items.length) { list.innerHTML = '<p class="empty-state">No active reminders.</p>'; return; }
    items.forEach(r => {
      const card = document.createElement("div");
      card.className = "task-card";
      card.innerHTML = `
        <div class="task-details">
          <p class="task-title">${escHtml(r.message || "Reminder")}</p>
          <div class="task-meta"><span>⏰ ${new Date(r.remind_at).toLocaleString()}</span></div>
        </div>
        <button class="delete-btn" data-id="${r.id}">✕</button>
      `;
      list.appendChild(card);
    });
    list.querySelectorAll(".delete-btn").forEach(btn => btn.addEventListener("click", async () => {
      try {
        await fetch(`${apiBase}/reminders/${btn.dataset.id}`, { method: "DELETE" });
        playBeep("success"); await loadReminders();
      } catch (err) { playBeep("error"); log(`Reminder delete failed: ${err.message}`); }
    }));
  } catch (err) { log(`Reminders fetch failed: ${err.message}`); }
}

async function createReminder() {
  const message = document.getElementById("reminder-message")?.value.trim();
  const remindAt = document.getElementById("reminder-datetime")?.value;
  if (!message || !remindAt) return;
  try {
    await fetchJson(`${apiBase}/reminders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, remind_at: remindAt }),
    });
    document.getElementById("reminder-message").value = "";
    document.getElementById("reminder-datetime").value = "";
    playBeep("success"); log(`Reminder set: "${message}"`); await loadReminders();
  } catch (err) { playBeep("error"); log(`Reminder create failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// POMODORO
// ═══════════════════════════════════════════════════════════════════════════════
function getPomodoroRemainingSeconds(session) {
  if (!session || !session.started_at) return 0;
  const start = new Date(session.started_at).getTime();
  const paused = (session.paused_secs || 0) * 1000;
  const extra = session.paused_at ? (Date.now() - new Date(session.paused_at).getTime()) : 0;
  const elapsed = Math.floor((Date.now() - start - paused - extra) / 1000);
  const total = (session.duration_min || 25) * 60;
  return Math.max(total - elapsed, 0);
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function renderPomodoroStatus(session) {
  if (pomodoroInterval) { clearInterval(pomodoroInterval); pomodoroInterval = null; }
  const box = document.getElementById("pomodoro-status");
  const pauseBtn = document.getElementById("pause-pomodoro-btn");
  const completeBtn = document.getElementById("complete-pomodoro-btn");
  const startBtn = document.getElementById("start-pomodoro-btn");

  if (!session) {
    if (box) box.innerHTML = '<p class="empty-state">No active session.</p>';
    if (pauseBtn) pauseBtn.disabled = true;
    if (completeBtn) completeBtn.disabled = true;
    if (startBtn) startBtn.disabled = false;
    return;
  }

  const remaining = getPomodoroRemainingSeconds(session);
  const isPaused = !!session.paused_at;
  if (box) {
    box.innerHTML = `
      <div class="task-card">
        <div class="task-details">
          <p class="task-title">${escHtml(session.task_title || "Pomodoro Session")}</p>
          <div class="task-meta">
            <span>⏱ ${session.duration_min} min</span>
            <span id="pomo-remaining">${isPaused ? "⏸ Paused" : `Remaining: ${formatTime(remaining)}`}</span>
          </div>
        </div>
      </div>
    `;
  }
  if (pauseBtn) { pauseBtn.disabled = false; pauseBtn.textContent = isPaused ? "▶ Resume" : "⏸ Pause"; }
  if (completeBtn) completeBtn.disabled = false;
  if (startBtn) startBtn.disabled = true;

  if (!isPaused && remaining > 0) {
    pomodoroInterval = setInterval(() => {
      if (!currentPomodoro) { clearInterval(pomodoroInterval); pomodoroInterval = null; return; }
      const rem = getPomodoroRemainingSeconds(currentPomodoro);
      const remEl = document.getElementById("pomo-remaining");
      if (remEl) {
        if (rem <= 0) {
          remEl.textContent = "⏰ Time's up!";
          playBeep("success");
          clearInterval(pomodoroInterval); pomodoroInterval = null;
        } else {
          remEl.textContent = `Remaining: ${formatTime(rem)}`;
        }
      }
      if (ScreenState.activeScreen === "pomodoro") renderScreen();
    }, 1000);
  }
}

async function loadActivePomodoro() {
  try {
    const s = await fetchJson(`${apiBase}/pomodoro/active`);
    currentPomodoro = {
      id: s.session_id, task_title: s.task_title,
      duration_min: s.duration_min, started_at: new Date(s.started_at),
      paused_at: s.paused_at ? new Date(s.paused_at) : null,
      paused_secs: s.paused_secs || 0,
    };
    renderPomodoroStatus(currentPomodoro);
  } catch { currentPomodoro = null; renderPomodoroStatus(null); }
}

async function loadPomodoroHistory() {
  try {
    const sessions = await fetchJson(`${apiBase}/pomodoro/history`);
    const list = document.getElementById("pomodoro-history");
    if (!list) return;
    list.innerHTML = "";
    if (!sessions.length) { list.innerHTML = '<p class="empty-state">No completed sessions.</p>'; return; }
    sessions.forEach(s => {
      const card = document.createElement("div");
      card.className = "task-card";
      const dur = s.ended_at && s.started_at
        ? Math.round((new Date(s.ended_at) - new Date(s.started_at)) / 60000)
        : s.duration_min;
      card.innerHTML = `
        <div class="task-details">
          <p class="task-title">${escHtml(s.task_title || "Session")}</p>
          <div class="task-meta">
            <span>✅ ${dur} min</span>
            ${s.ended_at ? `<span>${new Date(s.ended_at).toLocaleDateString()}</span>` : ""}
          </div>
        </div>
      `;
      list.appendChild(card);
    });
  } catch (err) { log(`Pomodoro history failed: ${err.message}`); }
}

async function startPomodoro() {
  const title = document.getElementById("pomodoro-task-title")?.value.trim();
  const duration = Number(document.getElementById("pomodoro-duration")?.value) || 25;
  try {
    const s = await fetchJson(`${apiBase}/pomodoro/start`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_title: title || null, duration_min: duration }),
    });
    currentPomodoro = {
      id: s.session_id, task_title: s.task_title,
      duration_min: s.duration_min, started_at: new Date(s.started_at),
      paused_at: null, paused_secs: 0,
    };
    if (document.getElementById("pomodoro-task-title")) document.getElementById("pomodoro-task-title").value = "";
    playBeep("success"); log(`Pomodoro started (${duration} min)`);
    renderPomodoroStatus(currentPomodoro); renderScreen();
  } catch (err) { playBeep("error"); log(`Pomodoro start failed: ${err.message}`); }
}

async function pauseOrResumePomodoro() {
  if (!currentPomodoro) return;
  const isPaused = !!currentPomodoro.paused_at;
  const endpoint = isPaused ? "resume" : "pause";
  try {
    await fetchJson(`${apiBase}/pomodoro/${currentPomodoro.id}/${endpoint}`, { method: "POST" });
    playBeep("click");
    if (isPaused) {
      currentPomodoro.paused_secs = (currentPomodoro.paused_secs || 0) + Math.round((Date.now() - new Date(currentPomodoro.paused_at).getTime()) / 1000);
      currentPomodoro.paused_at = null;
      log("Pomodoro resumed.");
    } else {
      currentPomodoro.paused_at = new Date();
      log("Pomodoro paused.");
    }
    renderPomodoroStatus(currentPomodoro); renderScreen();
  } catch (err) { playBeep("error"); log(`Pomodoro ${endpoint} failed: ${err.message}`); }
}

async function completePomodoro() {
  if (!currentPomodoro) return;
  try {
    await fetchJson(`${apiBase}/pomodoro/${currentPomodoro.id}/complete`, { method: "POST" });
    playBeep("success"); log(`Pomodoro completed: ${currentPomodoro.task_title || "session"}`);
    currentPomodoro = null;
    renderPomodoroStatus(null); renderScreen();
    await loadPomodoroHistory();
  } catch (err) { playBeep("error"); log(`Pomodoro complete failed: ${err.message}`); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HARDWARE SIMULATOR
// ═══════════════════════════════════════════════════════════════════════════════
function renderScreen() {
  const body = document.getElementById("screen-body");
  const headerTitle = document.getElementById("screen-header-title");
  const footerSheet = document.getElementById("screen-sheet-name");
  const footerAction = document.getElementById("screen-footer-action");
  if (!body) return;

  const TITLES = {
    home: "VOICEDESK", menu: "MENU", tasks: "TASKS", task_detail: "DETAIL",
    meetings: "MEETINGS", sheets: "SHEETS", notes: "NOTES", pomodoro: "POMODORO",
    settings: "SETTINGS", settings_info: "INFO", wifi: "WIFI",
    listening: "LISTENING", thinking: "THINKING", speaking: "ASSISTANT", reminders: "REMINDERS",
  };
  if (headerTitle) headerTitle.textContent = TITLES[ScreenState.activeScreen] || ScreenState.activeScreen.toUpperCase();

  const wifiText = (ws && ws.readyState === WebSocket.OPEN) ? "WiFi ✓" : "WiFi ✗";
  const syncText = systemStatus.sheets_connected ? "Sync ✓" : "Sync ✗";
  if (footerSheet) {
    if (ScreenState.activeScreen === "home") footerSheet.textContent = `[${wifiText}]`;
    else {
      const s = sheets.find(s => s.id === Number(selectedSheetId));
      footerSheet.textContent = s ? s.name.toUpperCase() : ScreenState.activeScreen.toUpperCase();
    }
  }
  if (footerAction) {
    const ACTION_MAP = {
      home: `[${syncText}]`, menu: "[OK=Open]", tasks: "[OK=Open]",
      task_detail: "[OK] Done [▼] Del", sheets: "[OK=Select]",
      settings: "[OK=Toggle]", wifi: "[OK=Connect]",
      pomodoro: currentPomodoro ? "[OK] Complete" : "[OK] Start",
    };
    footerAction.textContent = ACTION_MAP[ScreenState.activeScreen] || "";
  }

  body.innerHTML = "";

  if (ScreenState.activeScreen === "home") {
    body.innerHTML = `<div class="face-container face-idle"><div class="device-face"><div class="eyes"><div class="eye left-eye"></div><div class="eye right-eye"></div></div><div class="mouth smile"></div></div><div class="screen-instructions">Mode: ${currentMode.toUpperCase()}<br>Press MIC to talk</div></div>`;
    setFaceState("idle");
  } else if (ScreenState.activeScreen === "menu") {
    const ul = document.createElement("ul"); ul.className = "screen-list";
    ScreenState.menuItems.forEach((item, i) => {
      const li = document.createElement("li");
      li.className = i === ScreenState.activeItemIndex ? "selected" : "";
      li.innerHTML = `${i === ScreenState.activeItemIndex ? "► " : "&nbsp;&nbsp;"}${item.label}`;
      ul.appendChild(li);
    });
    body.appendChild(ul);
  } else if (ScreenState.activeScreen === "tasks") {
    const tasks = cachedTasks || [];
    if (!tasks.length) { body.innerHTML = '<p class="screen-empty">No tasks.<br>Press BACK.</p>'; }
    else {
      const ul = document.createElement("ul"); ul.className = "screen-list";
      tasks.forEach((task, i) => {
        const li = document.createElement("li");
        li.className = i === ScreenState.activeItemIndex ? "selected" : "";
        const cb = task.status === "done" ? "✓" : "○";
        li.innerHTML = `<div>${i === ScreenState.activeItemIndex ? "► " : "&nbsp;&nbsp;"}${cb} ${task.title}</div>`;
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
  } else if (ScreenState.activeScreen === "task_detail") {
    const task = ScreenState.selectedTask;
    if (!task) { ScreenState.activeScreen = "tasks"; renderScreen(); return; }
    body.innerHTML = `<div class="screen-detail"><div class="detail-title">${task.title}</div><div class="detail-row"><span>Status:</span><span>${task.status.toUpperCase()}</span></div><div class="detail-row"><span>Priority:</span><span>${task.priority.toUpperCase()}</span></div><div class="detail-row"><span>Due:</span><span>${task.due_date ? new Date(task.due_date).toLocaleDateString() : "—"}</span></div><div class="detail-actions"><div>[SELECT] Toggle</div><div>[DOWN] Delete</div></div></div>`;
  } else if (ScreenState.activeScreen === "meetings") {
    if (!cachedMeetings.length) { body.innerHTML = '<p class="screen-empty">No meetings.</p>'; }
    else {
      const ul = document.createElement("ul"); ul.className = "screen-list";
      cachedMeetings.forEach((m, i) => {
        const li = document.createElement("li");
        li.className = i === ScreenState.activeItemIndex ? "selected" : "";
        const dateStr = m.meeting_date ? new Date(m.meeting_date).toLocaleString([], {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}) : "";
        li.innerHTML = `<div>${i === ScreenState.activeItemIndex ? "► " : "&nbsp;&nbsp;"}${m.title}</div>${dateStr ? `<div style="font-size:.65rem;color:var(--screen-text-dim);margin-left:18px">${dateStr}</div>` : ""}`;
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
  } else if (ScreenState.activeScreen === "sheets") {
    if (!sheets.length) { body.innerHTML = '<p class="screen-empty">No sheets.</p>'; }
    else {
      const ul = document.createElement("ul"); ul.className = "screen-list";
      sheets.forEach((s, i) => {
        const li = document.createElement("li");
        const isCurrent = Number(selectedSheetId) === s.id;
        li.className = `${i === ScreenState.activeItemIndex ? "selected" : ""} ${isCurrent ? "active-sheet" : ""}`;
        li.innerHTML = `${i === ScreenState.activeItemIndex ? "► " : "&nbsp;&nbsp;"}${isCurrent ? "✓ " : ""}${s.name}`;
        ul.appendChild(li);
      });
      body.appendChild(ul);
    }
  } else if (ScreenState.activeScreen === "settings") {
    body.innerHTML = `<div class="screen-detail"><div class="detail-title">SYSTEM</div><div class="detail-row"><span>Mode:</span><span>${currentMode.toUpperCase()}</span></div><div class="detail-row"><span>Whisper:</span><span>${systemStatus.whisper_loaded ? "READY" : "OFFLINE"}</span></div><div class="detail-row"><span>Ollama:</span><span>${systemStatus.ollama_reachable ? "ONLINE" : "OFFLINE"}</span></div><div class="detail-row"><span>Sheets:</span><span>${systemStatus.sheets_connected ? "CONNECTED" : "OFFLINE"}</span></div></div>`;
  } else if (ScreenState.activeScreen === "pomodoro") {
    const remaining = currentPomodoro ? getPomodoroRemainingSeconds(currentPomodoro) : 1500;
    const total = currentPomodoro ? currentPomodoro.duration_min * 60 : 1500;
    const strokeDash = total > 0 ? (remaining / total) * 220 : 220;
    const isPaused = currentPomodoro?.paused_at;
    body.innerHTML = `<div class="screen-pomodoro"><div class="pomo-circle-container"><svg width="100" height="100" viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="35"></circle><circle class="fg" cx="50" cy="50" r="35" style="stroke-dasharray:220;stroke-dashoffset:${220-strokeDash}"></circle></svg><div class="pomo-timer">${isPaused ? "⏸" : formatTime(remaining)}</div></div><div class="pomo-task">${currentPomodoro ? (currentPomodoro.task_title || "Active") : "Standby"}</div><div class="pomo-actions">${currentPomodoro ? `<div>[SELECT] ${isPaused?"Resume":"Complete"}</div>` : "<div>[SELECT] Start</div>"}</div></div>`;
  } else if (ScreenState.activeScreen === "listening") {
    body.innerHTML = `<div class="face-container face-listening"><div class="device-face"><div class="eyes"><div class="eye left-eye"></div><div class="eye right-eye"></div></div><div class="mouth open"></div></div><canvas id="waveform-canvas" width="280" height="40"></canvas><div class="screen-instructions">Listening… release MIC</div></div>`;
    setFaceState("listening"); startWaveformAnimation();
  } else if (ScreenState.activeScreen === "thinking") {
    body.innerHTML = `<div class="face-container face-thinking"><div class="device-face"><div class="eyes"><div class="eye left-eye squint"></div><div class="eye right-eye squint"></div></div><div class="mouth line"></div></div><div class="screen-instructions">Thinking <span class="dot-bounce">. . .</span></div></div>`;
    setFaceState("thinking");
  } else if (ScreenState.activeScreen === "speaking") {
    body.innerHTML = `<div class="face-container face-speaking"><div class="device-face"><div class="eyes"><div class="eye left-eye"></div><div class="eye right-eye"></div></div><div class="mouth speak-mouth"></div></div><div class="screen-instructions speaking-bubble">${ScreenState.assistantBubbleText || "Speaking…"}</div></div>`;
    setFaceState("speaking");
  } else if (ScreenState.activeScreen === "wifi") {
    const ul = document.createElement("ul"); ul.className = "screen-list";
    ScreenState.wifiNetworks.forEach((net, i) => {
      const li = document.createElement("li");
      li.className = i === ScreenState.activeItemIndex ? "selected" : "";
      li.textContent = `${i === ScreenState.activeItemIndex ? "► " : "  "}${net.name}`;
      ul.appendChild(li);
    });
    body.appendChild(ul);
  } else if (ScreenState.activeScreen === "reminders") {
    body.innerHTML = '<p class="screen-empty">See Reminders panel on web dashboard.</p>';
  } else if (ScreenState.activeScreen === "notes") {
    body.innerHTML = '<p class="screen-empty">See Notes panel on web dashboard.</p>';
  }
}

function setFaceState(state) {
  ScreenState.faceState = state;
  const fc = document.querySelector(".face-container");
  if (fc) {
    fc.className = `face-container face-${state}`;
    const le = fc.querySelector(".left-eye");
    const re = fc.querySelector(".right-eye");
    const m = fc.querySelector(".mouth");
    if (le && re && m) {
      le.className = "eye left-eye"; re.className = "eye right-eye"; m.className = "mouth";
      if (state === "listening") m.classList.add("open");
      else if (state === "thinking") { le.classList.add("squint"); re.classList.add("squint"); m.classList.add("line"); }
      else if (state === "speaking") m.classList.add("speak-mouth");
      else if (state === "success") { re.classList.add("wink"); m.classList.add("smile"); }
      else if (state === "error") { m.classList.add("sad"); le.classList.add("error-eye"); re.classList.add("error-eye"); }
      else m.classList.add("smile");
    }
  }
}

function handleBtnBack() {
  playBeep("click");
  const backMap = { menu:"home", tasks:"menu", task_detail:"tasks", meetings:"menu", sheets:"menu", settings:"menu", wifi:"menu", pomodoro:"menu", speaking:"home", notes:"menu", reminders:"menu" };
  ScreenState.activeScreen = backMap[ScreenState.activeScreen] || "home";
  ScreenState.activeItemIndex = 0;
  renderScreen();
}

function handleBtnUp() {
  playBeep("click");
  if (ScreenState.activeScreen === "speaking") { ScreenState.activeScreen = "home"; if (fallbackHomeTimeout) clearTimeout(fallbackHomeTimeout); if (activeAudio) { activeAudio.pause(); activeAudio = null; } renderScreen(); return; }
  const lenMap = { menu: ScreenState.menuItems.length, tasks: cachedTasks.length, meetings: cachedMeetings.length, sheets: sheets.length, wifi: ScreenState.wifiNetworks.length, settings: ScreenState.settingsItems.length };
  const len = lenMap[ScreenState.activeScreen];
  if (len) ScreenState.activeItemIndex = (ScreenState.activeItemIndex - 1 + len) % len;
  renderScreen();
}

function handleBtnDown() {
  playBeep("click");
  if (ScreenState.activeScreen === "speaking") { ScreenState.activeScreen = "home"; if (fallbackHomeTimeout) clearTimeout(fallbackHomeTimeout); if (activeAudio) { activeAudio.pause(); activeAudio = null; } renderScreen(); return; }
  if (ScreenState.activeScreen === "task_detail") { deleteCurrentTask(); return; }
  if (ScreenState.activeScreen === "pomodoro" && currentPomodoro) { completePomodoro(); return; }
  const lenMap = { menu: ScreenState.menuItems.length, tasks: cachedTasks.length, meetings: cachedMeetings.length, sheets: sheets.length, wifi: ScreenState.wifiNetworks.length, settings: ScreenState.settingsItems.length };
  const len = lenMap[ScreenState.activeScreen];
  if (len) ScreenState.activeItemIndex = (ScreenState.activeItemIndex + 1) % len;
  renderScreen();
}

async function handleBtnOk() {
  playBeep("click");
  if (ScreenState.activeScreen === "home") { ScreenState.activeScreen = "menu"; ScreenState.activeItemIndex = 0; }
  else if (ScreenState.activeScreen === "menu") {
    const val = ScreenState.menuItems[ScreenState.activeItemIndex].value;
    ScreenState.activeScreen = val; ScreenState.activeItemIndex = 0;
    if (val === "meetings") await loadMeetings();
    if (val === "tasks") await loadTasks();
  } else if (ScreenState.activeScreen === "tasks") {
    if (cachedTasks.length > 0) { ScreenState.selectedTask = cachedTasks[ScreenState.activeItemIndex]; ScreenState.activeScreen = "task_detail"; }
  } else if (ScreenState.activeScreen === "sheets") {
    if (sheets.length > 0) {
      selectedSheetId = sheets[ScreenState.activeItemIndex].id;
      const sel = document.getElementById("sheet-select"); if (sel) sel.value = selectedSheetId;
      playBeep("success"); await loadTasks(); ScreenState.activeScreen = "tasks"; ScreenState.activeItemIndex = 0;
    }
  } else if (ScreenState.activeScreen === "task_detail") { await toggleCompleteCurrentTask(); return; }
  else if (ScreenState.activeScreen === "pomodoro") { if (currentPomodoro) await completePomodoro(); else await startPomodoroSimulator(); }
  else if (ScreenState.activeScreen === "settings") {
    const item = ScreenState.settingsItems[ScreenState.activeItemIndex];
    if (item.key === "sync") { await triggerManualSync(); }
    else if (item.key === "clearCache") { localStorage.clear(); cachedTasks = []; cachedMeetings = []; playBeep("success"); log("Cache cleared."); }
    else if (item.key === "sysInfo") { await loadStatus(); }
  }
  renderScreen();
}

async function startPomodoroSimulator() {
  try {
    const s = await fetchJson(`${apiBase}/pomodoro/start`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_title: "Hardware Session", duration_min: 25 }),
    });
    currentPomodoro = { id: s.session_id, task_title: s.task_title, duration_min: s.duration_min, started_at: new Date(s.started_at), paused_at: null, paused_secs: 0 };
    playBeep("success"); renderPomodoroStatus(currentPomodoro); renderScreen();
  } catch (err) { playBeep("error"); log(`Pomodoro start failed: ${err.message}`); }
}

async function toggleCompleteCurrentTask() {
  const task = ScreenState.selectedTask; if (!task) return;
  const newStatus = task.status === "done" ? "pending" : "done";
  try {
    await fetchJson(`${apiBase}/tasks/${task.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: newStatus }) });
    playBeep("success"); setFaceState("success"); await loadTasks();
    setTimeout(() => { ScreenState.activeScreen = "tasks"; renderScreen(); }, 1200);
  } catch (err) { playBeep("error"); setFaceState("error"); setTimeout(() => renderScreen(), 1500); }
}

async function deleteCurrentTask() {
  const task = ScreenState.selectedTask; if (!task) return;
  try {
    await fetch(`${apiBase}/tasks/${task.id}`, { method: "DELETE" });
    playBeep("success"); setFaceState("success"); await loadTasks();
    setTimeout(() => { ScreenState.activeScreen = "tasks"; renderScreen(); }, 1200);
  } catch (err) { playBeep("error"); setFaceState("error"); setTimeout(() => renderScreen(), 1500); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// WEBSOCKET & AUDIO
// ═══════════════════════════════════════════════════════════════════════════════
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  if (wsConnecting) return;
  wsConnecting = true;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/ws/audio`;
  log(`Connecting WebSocket: ${wsUrl}`);
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsConnecting = false;
    const cs = document.getElementById("connection-status"); if (cs) cs.textContent = "Connected";
    const pi = document.getElementById("ping-indicator"); if (pi) pi.classList.remove("offline");
    log("WebSocket connected ✓");
  };

  ws.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "status") {
        log(`Server: ${data.status} ${data.detail || ""}`);
        const footerEl = document.getElementById("screen-sheet-name");
        if (footerEl && ScreenState.activeScreen !== "home") footerEl.textContent = data.status.toUpperCase().slice(0, 14);
        if (data.status.includes("Thinking") || data.status.includes("Transcribing") || data.status.includes("Understanding") || data.status.includes("Syncing")) setFaceState("thinking");
        else if (data.status.includes("Generating") || data.status.includes("Responding")) setFaceState("thinking");
      } else if (data.type === "state") {
        if (data.face) setFaceState(data.face);
      } else if (data.type === "transcript") {
        log(`Heard: "${data.text}"`);
        renderChatMessage("User", data.text);
      } else if (data.type === "search_results") {
        log(`Search: ${data.count} results for "${data.query}"`);
        renderChatMessage("Search", `Found ${data.count} results for: "${data.query}"`);
      } else if (data.type === "response" || data.type === "clarification") {
        log(`Intent: ${data.intent} | Latency: ${data.latency_ms}ms`);
        if (data.mode) updateModeUI(data.mode);
        renderChatMessage("Assistant", data.response_text || data.question || "", data.suggested_followups);
        ScreenState.activeScreen = "speaking";
        renderScreen();
        typeTextOnScreen(data.response_text || data.question || "…", 20, () => {
          if (data.type === "clarification") fallbackHomeTimeout = setTimeout(() => startRecordingAndStream(), 1000);
        });
        if (data.audio_file) playAudio(data.audio_file, () => { if (data.type === "clarification") startRecordingAndStream(); else setFaceState("success"); });
        await Promise.all([loadSheets(), loadTasks(), loadReminders(), loadActivePomodoro(), loadMeetings(), loadStatus()]);
      } else if (data.type === "audio") {
        if (data.audio_file) playAudio(data.audio_file, () => { if (currentResponseIsClarification) startRecordingAndStream(); else setFaceState("success"); });
      } else if (data.type === "error") {
        log(`Error: ${data.response_text || data.message}`);
        renderChatMessage("Error", data.response_text || data.message || "Unknown error");
        setFaceState("error"); playBeep("error");
        setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 3000);
      }
    } catch (err) { log(`WS parse error: ${err.message}`); }
  };

  ws.onclose = () => {
    wsConnecting = false;
    const cs = document.getElementById("connection-status"); if (cs) cs.textContent = "Disconnected";
    const pi = document.getElementById("ping-indicator"); if (pi) pi.classList.add("offline");
    log("WebSocket closed. Reconnecting in 5s…");
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = () => { wsConnecting = false; log("WebSocket error."); };
}

function resample(buffer, fromRate, toRate) {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const newLen = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLen);
  let oi = 0, ob = 0;
  while (oi < result.length) {
    const nb = Math.round((oi + 1) * ratio);
    let acc = 0, cnt = 0;
    for (let i = ob; i < nb && i < buffer.length; i++) { acc += buffer[i]; cnt++; }
    result[oi] = cnt > 0 ? acc / cnt : 0;
    oi++; ob = nb;
  }
  return result;
}

async function startRecordingAndStream() {
  if (isRecording) return;
  isRecording = true;
  playBeep("click");
  if (activeAudio) { activeAudio.pause(); activeAudio = null; }
  const micBtn = document.getElementById("hw-btn-mic");
  if (micBtn) micBtn.classList.add("recording");
  ScreenState.activeScreen = "listening"; renderScreen();
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser(); analyser.fftSize = 256;
    dataArray = new Uint8Array(analyser.frequencyBinCount);
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(processor); processor.connect(audioContext.destination);
    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      const resampled = resample(inputData, audioContext.sampleRate, 16000);
      const pcm16 = new Int16Array(resampled.length);
      for (let i = 0; i < resampled.length; i++) {
        const s = Math.max(-1, Math.min(1, resampled[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(pcm16.buffer);
    };
    startWaveformAnimation();
    log("Recording… release MIC to send.");
  } catch (err) {
    isRecording = false;
    if (micBtn) micBtn.classList.remove("recording");
    log(`Mic error: ${err.message}`); playBeep("error");
    ScreenState.activeScreen = "home"; renderScreen();
  }
}

function stopRecordingAndSend() {
  if (!isRecording) return;
  isRecording = false; playBeep("click");
  const micBtn = document.getElementById("hw-btn-mic");
  if (micBtn) micBtn.classList.remove("recording");
  ScreenState.activeScreen = "thinking"; renderScreen();
  if (processor) { processor.disconnect(); processor = null; }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  if (audioContext) { audioContext.close(); audioContext = null; }
  analyser = null;
  if (animationId) { cancelAnimationFrame(animationId); animationId = null; }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "audio_end" }));
    log("Audio sent. Awaiting response…");
  } else {
    log("WebSocket closed — cannot process."); setFaceState("error");
    setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 2000);
  }
}

function startWaveformAnimation() {
  const canvas = document.getElementById("waveform-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  if (animationId) cancelAnimationFrame(animationId);
  function draw() {
    animationId = requestAnimationFrame(draw);
    ctx.fillStyle = "#050b18"; ctx.fillRect(0, 0, w, h);
    ctx.lineWidth = 2; ctx.strokeStyle = "#00ffcc"; ctx.beginPath();
    if (analyser) {
      analyser.getByteTimeDomainData(dataArray);
      const sw = w / dataArray.length; let x = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0, y = v * h / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        x += sw;
      }
    } else {
      ctx.moveTo(0, h/2);
      for (let x = 0; x < w; x++) ctx.lineTo(x, h/2 + Math.sin(x * 0.08 + Date.now() * 0.015) * 3);
    }
    ctx.stroke();
  }
  draw();
}

function typeTextOnScreen(text, speed = 20, callback = null) {
  if (typingTimer) clearInterval(typingTimer);
  ScreenState.activeScreen = "speaking"; ScreenState.assistantBubbleText = "";
  let i = 0;
  typingTimer = setInterval(() => {
    if (i < text.length) {
      ScreenState.assistantBubbleText += text.charAt(i); i++;
      const bubble = document.querySelector(".speaking-bubble");
      if (bubble) bubble.textContent = ScreenState.assistantBubbleText; else renderScreen();
    } else {
      clearInterval(typingTimer); typingTimer = null;
      if (callback) callback();
    }
  }, speed);
}

function playAudio(filename, onEndCallback = null) {
  if (activeAudio) { activeAudio.pause(); activeAudio = null; }
  activeAudio = new Audio(`/api/audio/${filename}`);
  let speakInterval = null;
  activeAudio.addEventListener("play", () => {
    setFaceState("speaking");
    const mouth = document.querySelector(".mouth.speak-mouth");
    if (mouth) {
      speakInterval = setInterval(() => {
        const h = [4,8,14,18,22,16,10][Math.floor(Math.random()*7)];
        mouth.style.height = `${h}px`;
        mouth.style.borderRadius = h > 12 ? "50%" : "0 0 16px 16px";
      }, 100);
    }
  });
  activeAudio.addEventListener("ended", () => {
    if (speakInterval) clearInterval(speakInterval);
    activeAudio = null; playBeep("success");
    if (onEndCallback) onEndCallback(); else setFaceState("idle");
  });
  activeAudio.addEventListener("error", () => {
    if (speakInterval) clearInterval(speakInterval);
    activeAudio = null; setFaceState("error");
    setTimeout(() => setFaceState("idle"), 2000);
  });
  activeAudio.play().catch(err => { log(`Audio error: ${err.message}`); activeAudio = null; });
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHAT
// ═══════════════════════════════════════════════════════════════════════════════
function renderChatMessage(role, text, followups = null) {
  const chatLog = document.getElementById("chat-log");
  if (!chatLog) return;
  const c = document.createElement("div");
  c.className = "chat-message-container " + role.toLowerCase();
  const p = document.createElement("p");
  p.innerHTML = `<strong>${role}:</strong> ${escHtml(text)}`;
  c.appendChild(p);
  if (followups && followups.length) {
    const btns = document.createElement("div"); btns.className = "followup-buttons";
    followups.forEach(f => {
      if (!f) return;
      const btn = document.createElement("button"); btn.className = "followup-btn";
      btn.textContent = f;
      btn.addEventListener("click", () => { document.getElementById("chat-input").value = f; sendChat(); });
      btns.appendChild(btn);
    });
    c.appendChild(btns);
  }
  chatLog.prepend(c);
}

async function sendChat() {
  const inputEl = document.getElementById("chat-input");
  const txt = inputEl?.value.trim();
  if (!txt) return;
  renderChatMessage("User", txt);
  if (inputEl) inputEl.value = "";
  ScreenState.activeScreen = "thinking"; renderScreen();

  try {
    const shouldExecute = document.getElementById("execute-toggle")?.checked ?? true;
    chatHistory.push({ role: "user", content: txt });
    chatHistory = chatHistory.slice(-10);

    if (shouldExecute) {
      const res = await fetchJson(`${apiBase}/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: txt, available_sheets: sheets.map(s=>s.name), execute: true, history: chatHistory, session_id: sessionId }),
      });
      renderChatMessage("Assistant", res.assistant || "", res.parsed?.suggested_followups);
      if (res.assistant) { chatHistory.push({ role: "assistant", content: res.assistant }); chatHistory = chatHistory.slice(-10); }
      ScreenState.activeScreen = "speaking"; ScreenState.assistantBubbleText = res.assistant || "";
      renderScreen();
      if (res.audio_file) playAudio(res.audio_file, () => { setFaceState("success"); setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 1500); });
      else setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 3000);
      await Promise.all([loadSheets(), loadTasks(), loadReminders(), loadActivePomodoro()]);
    } else {
      const parsed = await fetchJson(`${apiBase}/parse_intent`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: txt, available_sheets: sheets.map(s=>s.name), history: chatHistory }),
      });
      renderChatMessage("Parse", JSON.stringify(parsed));
      const gen = await fetchJson(`${apiBase}/generate_response`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_summary: txt, follow_up: null }),
      });
      renderChatMessage("Assistant", gen.response || "");
      ScreenState.activeScreen = "speaking"; ScreenState.assistantBubbleText = gen.response || ""; renderScreen();
      setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 3000);
    }
  } catch (err) {
    renderChatMessage("Error", err.message);
    setFaceState("error"); playBeep("error");
    setTimeout(() => { ScreenState.activeScreen = "home"; renderScreen(); }, 2000);
  }
}

async function triggerManualSync() {
  const syncIcon = document.getElementById("screen-sync-icon");
  if (syncIcon) syncIcon.className = "syncing";
  log("Syncing Google Sheets…");
  try {
    const res = await fetchJson(`${apiBase}/sync`, { method: "POST" });
    playBeep("success"); log(res.message || "Sync complete.");
  } catch (err) { playBeep("error"); log(`Sync failed: ${err.message}`); }
  finally { if (syncIcon) syncIcon.className = "sync-idle"; }
}

function startScreenClock() {
  function tick() {
    const el = document.getElementById("screen-time-display");
    if (el) { const n = new Date(); el.textContent = `${n.getHours().toString().padStart(2,"0")}:${n.getMinutes().toString().padStart(2,"0")}`; }
  }
  setInterval(tick, 1000); tick();
}

function escHtml(s) {
  if (!s) return "";
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ═══════════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════════
async function init() {
  if (window.location.protocol === "file:") {
    const b = document.getElementById("warning-banner"); if (b) b.classList.remove("hidden");
    return;
  }

  // Nav buttons
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => switchPanel(btn.dataset.panel));
  });

  // Mode pills
  document.querySelectorAll(".mode-pill").forEach(pill => {
    pill.addEventListener("click", () => setMode(pill.dataset.mode));
  });

  // Task panel
  document.getElementById("create-task-btn")?.addEventListener("click", createTask);
  document.getElementById("refresh-tasks")?.addEventListener("click", loadTasks);
  document.getElementById("task-status-filter")?.addEventListener("change", loadTasks);
  document.getElementById("sheet-select")?.addEventListener("change", async (e) => { selectedSheetId = e.target.value; await loadTasks(); });
  document.getElementById("create-sheet-btn")?.addEventListener("click", createSheet);
  document.getElementById("force-sync-btn")?.addEventListener("click", triggerManualSync);

  // Notes panel
  document.getElementById("note-save-btn")?.addEventListener("click", saveNote);
  document.getElementById("note-clear-btn")?.addEventListener("click", clearNoteEditor);
  document.getElementById("refresh-notes")?.addEventListener("click", loadNotes);
  document.getElementById("note-search")?.addEventListener("input", () => { clearTimeout(window._noteSearchTimer); window._noteSearchTimer = setTimeout(loadNotes, 350); });

  // Meetings panel
  document.getElementById("create-meeting-btn")?.addEventListener("click", createMeeting);
  document.getElementById("refresh-meetings")?.addEventListener("click", loadMeetings);

  // Reminders panel
  document.getElementById("create-reminder-btn")?.addEventListener("click", createReminder);
  document.getElementById("refresh-reminders")?.addEventListener("click", loadReminders);

  // Pomodoro panel
  document.getElementById("start-pomodoro-btn")?.addEventListener("click", startPomodoro);
  document.getElementById("pause-pomodoro-btn")?.addEventListener("click", pauseOrResumePomodoro);
  document.getElementById("complete-pomodoro-btn")?.addEventListener("click", completePomodoro);

  // Chat
  document.getElementById("chat-send")?.addEventListener("click", sendChat);
  document.getElementById("chat-input")?.addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });

  // Hardware buttons
  document.getElementById("hw-btn-back")?.addEventListener("click", handleBtnBack);
  document.getElementById("hw-btn-up")?.addEventListener("click", handleBtnUp);
  document.getElementById("hw-btn-down")?.addEventListener("click", handleBtnDown);
  document.getElementById("hw-btn-ok")?.addEventListener("click", handleBtnOk);

  // PTT hold-to-talk
  let micLongPressTimer = null, micStartTime = null;
  const LONG_PRESS = 1500;
  const micBtn = document.getElementById("hw-btn-mic");
  if (micBtn) {
    micBtn.addEventListener("mousedown", e => { e.preventDefault(); micStartTime = Date.now(); micLongPressTimer = setTimeout(() => { playBeep("success"); log("Always-listen toggled."); }, LONG_PRESS); startRecordingAndStream(); });
    micBtn.addEventListener("mouseup", e => { e.preventDefault(); if (micLongPressTimer) { clearTimeout(micLongPressTimer); micLongPressTimer = null; } if (Date.now() - micStartTime < LONG_PRESS) stopRecordingAndSend(); });
    micBtn.addEventListener("mouseleave", e => { e.preventDefault(); if (micLongPressTimer) { clearTimeout(micLongPressTimer); micLongPressTimer = null; } stopRecordingAndSend(); });
    micBtn.addEventListener("touchstart", e => { e.preventDefault(); micStartTime = Date.now(); micLongPressTimer = setTimeout(() => playBeep("success"), LONG_PRESS); startRecordingAndStream(); });
    micBtn.addEventListener("touchend", e => { e.preventDefault(); if (micLongPressTimer) { clearTimeout(micLongPressTimer); micLongPressTimer = null; } if (Date.now() - micStartTime < LONG_PRESS) stopRecordingAndSend(); });
  }

  // Start core services
  connectWebSocket();
  startScreenClock();

  await loadStatus();
  await loadSheets();
  await loadTasks();
  await loadReminders();
  await loadActivePomodoro();
  await loadMeetings();

  renderScreen();
  setInterval(loadStatus, 15000);
}

init().catch(err => log(`Init error: ${err.message}`));
