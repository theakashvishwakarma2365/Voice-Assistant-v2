# VoiceDesk — System Architecture
### Handheld Voice Productivity Assistant
**ESP32 Device + Raspberry Pi 5 Server + Google Sheets**

---

## 1. System Overview

VoiceDesk is a two-tier, always-on voice productivity system:

- **Tier 1 — ESP32 Handheld Device:** Captures wake word + audio, streams to server, displays UI on 3.5" touchscreen, plays back TTS audio. Thin client — no heavy processing on device.
- **Tier 2 — Raspberry Pi 5 Server (Local):** Runs all AI models (Whisper STT, Ollama LLM, TTS), maintains SQLite database, syncs with Google Sheets, exposes a REST/WebSocket API.

All AI inference stays **local on your network** — no cloud required for core functionality.

---

## 2. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  ESP32 HANDHELD DEVICE                  │
│                                                         │
│  [INMP441 Mic] ──► [Audio Buffer]                      │
│                         │                               │
│  [Wake Word Engine]◄────┤                               │
│  (Porcupine/local)      │ wake detected                 │
│                         ▼                               │
│              [WebSocket Client]──────────────────────►  │
│                         ▲         Audio stream (PCM)    │
│  [MAX98357A Speaker]◄───┤                               │
│                         │ TTS audio back                │
│  [XPT2046 Display] ◄────┤                               │
│                    JSON UI updates                      │
└─────────────────────────────────────────────────────────┘
                          │  WiFi (LAN)
                          ▼
┌─────────────────────────────────────────────────────────┐
│               RASPBERRY PI 5 SERVER                     │
│                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐  │
│  │  FastAPI    │   │  Whisper STT │   │  Ollama LLM │  │
│  │  Server     │──►│  (base/small)│──►│  (phi3/     │  │
│  │  :8000      │   │              │   │  mistral)   │  │
│  └─────────────┘   └──────────────┘   └─────────────┘  │
│         │                                    │          │
│         ▼                                    ▼          │
│  ┌─────────────┐                   ┌─────────────────┐  │
│  │  SQLite DB  │◄──────────────────│  Intent Engine  │  │
│  │  (tasks,    │                   │  (parse voice   │  │
│  │  projects,  │                   │  commands into  │  │
│  │  sheets,    │                   │  structured     │  │
│  │  reminders) │                   │  actions)       │  │
│  └─────────────┘                   └─────────────────┘  │
│         │                                    │          │
│         ▼                                    ▼          │
│  ┌─────────────┐                   ┌─────────────────┐  │
│  │  Google     │                   │  TTS Engine     │  │
│  │  Sheets API │                   │  (Piper / edge  │  │
│  │  Sync       │                   │  TTS)           │  │
│  └─────────────┘                   └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
                ┌──────────────────┐
                │  Google Sheets   │
                │  (your existing  │
                │   spreadsheets)  │
                └──────────────────┘
```

---

## 3. Component Breakdown

### 3A. ESP32 Device (Thin Client)

| Layer | Technology | Role |
|-------|-----------|------|
| Audio capture | INMP441 → I2S0 | Record PCM audio at 16kHz |
| Wake word | Porcupine SDK (offline) | Detect "Hey Desk" without server |
| Display | ILI9341 + XPT2046 / TFT_eSPI | Show status, task lists, confirmations |
| Network | WiFi + WebSocket | Stream audio to Pi5, receive responses |
| Playback | MAX98357A → I2S1 | Play TTS audio response |
| Power | Li-Po 3000mAh + TP4056 | Rechargeable |

**ESP32 responsibilities (only):**
- Detect wake word locally (Porcupine runs on-device, ~30KB model)
- Stream audio PCM to Pi5 over WebSocket
- Receive JSON display updates + MP3/WAV audio from Pi5
- Render UI on touchscreen
- Handle touch input → send commands

**ESP32 does NOT do:** STT, LLM inference, DB access, Google Sheets — all on Pi5.

---

### 3B. Raspberry Pi 5 Server

#### API Layer — FastAPI (Python)
```
Endpoints:
  WS  /ws/audio          ← receive audio stream from ESP32
  POST /api/command       ← text command (fallback/testing)
  GET  /api/tasks         ← fetch task list for display
  GET  /api/projects      ← fetch projects/sheets list
  POST /api/sync          ← force Google Sheets sync
  GET  /api/status        ← server health
```

#### AI Pipeline (per voice command)
```
Audio PCM (16kHz)
     │
     ▼
[Whisper STT] ── transcribes speech to text
     │
     ▼
[Intent Parser / Ollama LLM]
  - Classifies intent: ADD_TASK | DELETE_TASK | QUERY | SCHEDULE_MEETING |
                        NEW_SHEET | SWITCH_SHEET | SET_REMINDER | POMODORO
  - Extracts entities: date, time, title, project, sheet_name, remarks
  - Asks clarifying questions if info incomplete
  - Suggests smart additions (renewal reminders, follow-ups)
     │
     ▼
[Action Executor]
  - Writes to SQLite DB
  - Syncs to Google Sheets (correct sheet/tab)
  - Schedules reminders
     │
     ▼
[Response Generator / Ollama]
  - Generates natural language confirmation
  - "Done! Added 'Meeting with John' to Project Alpha sheet for Monday 10am.
     Want me to set a reminder 30 minutes before?"
     │
     ▼
[TTS Engine (Piper)]
  - Converts text to WAV audio
     │
     ▼
[WebSocket → ESP32]
  - Sends audio + JSON display payload
```

---

## 4. Data Architecture

### SQLite Database Schema (on Pi5)

```sql
-- Sheets = your Google Sheets tabs (one per project/category)
CREATE TABLE sheets (
  id INTEGER PRIMARY KEY,
  name TEXT,                    -- "Work", "Personal", "Seed Form"
  google_sheet_id TEXT,         -- Google Sheets file ID
  tab_name TEXT,                -- specific tab/sheet name
  created_at DATETIME,
  last_synced DATETIME
);

-- Tasks
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  sheet_id INTEGER REFERENCES sheets(id),
  title TEXT NOT NULL,
  status TEXT DEFAULT 'pending', -- pending | in_progress | done | cancelled
  due_date DATETIME,
  remarks TEXT,
  created_at DATETIME,
  updated_at DATETIME,
  synced_to_sheets BOOLEAN DEFAULT FALSE
);

-- Meetings
CREATE TABLE meetings (
  id INTEGER PRIMARY KEY,
  sheet_id INTEGER REFERENCES sheets(id),
  title TEXT,
  date DATETIME,
  participants TEXT,            -- JSON array
  remarks TEXT,
  renewal_reminder BOOLEAN DEFAULT FALSE,
  renewal_date DATETIME,
  created_at DATETIME
);

-- Reminders
CREATE TABLE reminders (
  id INTEGER PRIMARY KEY,
  task_id INTEGER,
  meeting_id INTEGER,
  remind_at DATETIME,
  message TEXT,
  delivered BOOLEAN DEFAULT FALSE
);

-- Voice Command Log (for debugging + learning)
CREATE TABLE command_log (
  id INTEGER PRIMARY KEY,
  raw_transcript TEXT,
  intent TEXT,
  entities_json TEXT,
  success BOOLEAN,
  created_at DATETIME
);
```

### Google Sheets Sync Strategy
- **SQLite is the source of truth** on device
- Sync to Google Sheets every 60 seconds (background thread) + on every write
- Each "sheet" in the app = one Tab in your Google Spreadsheet
- Columns auto-created: Title | Status | Due Date | Remarks | Created | Updated

---

## 5. Voice Command Flow Examples

### "Schedule a meeting with Rahul next Monday at 3pm"
```
STT      → "Schedule a meeting with Rahul next Monday at 3pm"
Intent   → SCHEDULE_MEETING
Entities → { title: "Meeting with Rahul", date: "2026-06-08", time: "15:00" }
Missing  → which sheet/project?
Response → "Which project should I add this to — Work, Personal, or Seed Form?"
User     → "Work"
Action   → INSERT into meetings (sheet=Work, date=Mon 3pm)
           SYNC to Google Sheets tab "Work"
Follow-up→ "Done! Also, should I set a reminder before the meeting?
            And would you like to add renewal or follow-up for this?"
```

### "Add task: Review Seed Form documents by Friday"
```
STT      → "Add task review seed form documents by Friday"
Intent   → ADD_TASK
Entities → { title: "Review Seed Form documents", due: "2026-06-05",
             sheet_hint: "Seed Form" }
Action   → INSERT into tasks (sheet=Seed Form, due=Friday)
Response → "Added to Seed Form sheet. Due this Friday. Any remarks to add?"
```

### "What's pending in Project Alpha?"
```
Intent   → QUERY_TASKS
Entities → { sheet: "Project Alpha", status: "pending" }
Action   → SELECT from tasks WHERE sheet=Project Alpha AND status=pending
Response → "You have 3 pending tasks in Project Alpha:
            1. Send proposal — due tomorrow
            2. Review contract — no due date
            3. Follow up with client — overdue by 2 days"
Display  → Task list shown on ESP32 screen
```

---

## 6. Ollama Model Recommendation

| Model | RAM Usage | Speed on Pi5 | Best For |
|-------|-----------|-------------|----------|
| **phi3:mini** (3.8B) | ~2.5GB | ~2-3 sec/response | ✅ Recommended — fast, smart enough |
| mistral:7b | ~4.5GB | ~6-8 sec/response | More capable, slower |
| llama3.2:3b | ~2GB | ~1-2 sec/response | Fastest, slightly less smart |
| gemma2:2b | ~1.8GB | ~1 sec/response | Backup option |

**Recommendation: `phi3:mini`** for intent parsing + response generation.
Use a **system prompt** that constrains it to your task schema — don't let it freestyle.

---

## 7. Raspberry Pi 5 (4GB) — What You Have vs What You Need

### Current: Pi 5 4GB

| Resource | Available | Required | Status |
|----------|-----------|----------|--------|
| RAM | 4GB | ~3GB (Whisper + Ollama + FastAPI) | ✅ Tight but OK |
| Storage | depends | 32GB+ recommended | ⚠️ Check |
| CPU | Quad A76 | Heavy for real-time audio | ✅ Good enough |
| GPU/NPU | None | None needed | ✅ |

### Upgrades to Make

| Upgrade | Cost | Priority | Why |
|---------|------|----------|-----|
| **NVMe SSD via M.2 HAT** | ~$15-25 | 🔴 High | SD card too slow for Whisper model loading + SQLite writes. NVMe = 10× faster |
| **Active cooler / fan** | ~$5 | 🔴 High | Pi5 throttles under sustained AI load without cooling |
| **32GB+ fast microSD** (if no NVMe) | ~$10 | 🟡 Medium | Minimum if skipping NVMe |
| **Pi 5 8GB upgrade** | ~$30 extra | 🟡 Medium | Run mistral 7B comfortably. 4GB works with phi3 |
| **UPS HAT (for Pi5)** | ~$20 | 🟢 Optional | Keeps server alive during power cuts |

### Software Stack on Pi5
```
OS:        Raspberry Pi OS Lite (64-bit, no desktop needed)
Runtime:   Python 3.11
Server:    FastAPI + Uvicorn
STT:       faster-whisper (base.en or small.en model)
LLM:       Ollama + phi3:mini
TTS:       Piper TTS (fast, offline, natural voice)
DB:        SQLite + SQLAlchemy
Sheets:    gspread (Python Google Sheets library)
Scheduler: APScheduler (reminders, sync jobs)
WakeWord:  Porcupine (on ESP32, not Pi)
```

---

## 8. One-Time Setup Flow (ESP32)

```
1. Flash ESP32 firmware (Arduino / ESP-IDF)
2. First boot → shows WiFi config screen on display
3. User enters WiFi credentials via touchscreen
4. ESP32 connects → discovers Pi5 server via mDNS (voicedesk.local)
5. Handshake → Pi5 sends config (sheet list, wake word model)
6. Google Sheets OAuth → done ONCE on Pi5 web interface (http://voicedesk.local:8000)
7. Device is ready — all future config via voice
```

---

## 9. Feature Roadmap

### Phase 1 — MVP (Build First)
- [x] Wake word detection on ESP32
- [x] Audio streaming to Pi5
- [x] Whisper STT
- [x] Basic intent parsing (add/delete/query task)
- [x] SQLite persistence
- [x] Google Sheets sync (one sheet)
- [x] TTS response + playback
- [x] Display: task list + status

### Phase 2 — Smart Features
- [ ] Multi-sheet support (create/switch sheets by voice)
- [ ] Meeting scheduling with reminders
- [ ] Renewal/follow-up suggestions
- [ ] Pomodoro timer (voice start/stop)
- [ ] "What's my day look like?" morning briefing

### Phase 3 — Advanced
- [ ] Recurring tasks
- [ ] Project health summaries
- [ ] Calendar integration (Google Calendar)
- [ ] Offline mode (Pi5 unreachable fallback)
- [ ] Web dashboard (view from phone)

---

## 10. Summary — Why This Architecture Wins

| Concern | Solution |
|---------|---------|
| ESP32 too weak for AI | ESP32 = thin client only; all AI on Pi5 |
| Privacy | All models run locally; nothing leaves your network |
| Google Sheets integration | gspread library, OAuth once, auto-sync |
| Multiple sheets/projects | SQLite maps each "sheet" to a Google Sheets tab |
| Intelligent suggestions | Ollama phi3 generates contextual follow-ups |
| Voice-only operation | Full command set, no touch required |
| Expandability | FastAPI means any new feature = new endpoint |
| Reliability | SQLite buffers if internet down; syncs when back |
