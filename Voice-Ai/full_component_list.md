# VoiceDesk — Complete Component List & UI Design
### Button-Controlled Handheld Voice Assistant

---

## 🔘 Button Layout (4 Buttons)

```
Physical placement on enclosure:

  ┌─────────────────────────┐
  │   ┌─────────────────┐   │
  │   │                 │   │
  │   │   3.5" Display  │   │
  │   │                 │   │
  │   └─────────────────┘   │
  │                         │
  │  [◄]  [▲]  [▼]  [OK]   │
  │  BACK  UP  DOWN  SELECT │
  │                         │
  │  [MIC] ← side button    │
  └─────────────────────────┘
```

| Button | Label | Short Press | Long Press |
|--------|-------|-------------|------------|
| BTN 1 | ◄ BACK | Go back / cancel | Go to home screen |
| BTN 2 | ▲ UP | Scroll up / prev item | — |
| BTN 3 | ▼ DOWN | Scroll down / next item | — |
| BTN 4 | ✓ OK/SELECT | Select / confirm | Open context menu |
| BTN 5 | 🎤 MIC | Hold to talk (PTT) | Toggle always-listen mode |

> **5 buttons total** — 4 navigation on front, 1 mic/PTT on side (like a walkie-talkie). Much better UX than 4-only.

---

## 📺 Display UI Screens

### Screen 1 — Home / Idle Face
```
┌─────────────────────────┐
│     VoiceDesk  11:42    │
│                         │
│        ◕  ◕             │  ← animated eyes (blink)
│          ‿              │  ← mouth changes with state
│                         │
│  "Say something or      │
│   press MIC to talk"    │
│                         │
│  [WiFi ✓]  [Sync ✓]    │
└─────────────────────────┘

Face States:
  IDLE     → normal eyes, slight smile  ◕‿◕
  LISTENING → wide eyes, open mouth     ◉ ◉  ○
  THINKING  → squinting, dots animate   ◑ ◑  ...
  SPEAKING  → happy, mouth bounces      ◕ ◕  ◡◡◡
  ERROR     → sad face                  ◔ ◔  ︵
  SUCCESS   → big smile + wink          ◕ ◉  ◡
```

### Screen 2 — Main Menu
```
┌─────────────────────────┐
│  ◄  MENU           ✓   │
│ ─────────────────────── │
│ ► 📋 Tasks              │
│   📅 Meetings           │
│   📁 Projects / Sheets  │
│   ⏱  Pomodoro           │
│   ⚙️  Settings          │
│   📶 WiFi               │
└─────────────────────────┘
```

### Screen 3 — Task List View
```
┌─────────────────────────┐
│  ◄  WORK SHEET     ✓   │
│ ─────────────────────── │
│ ► ○ Review contract     │
│     Due: Tomorrow       │
│   ○ Call Rahul          │
│     Due: Friday         │
│   ✓ Send proposal       │
│     Done 2 days ago     │
│ ─────────────────────── │
│  [▲▼ Navigate] [OK=Open]│
└─────────────────────────┘
```

### Screen 4 — Task Detail
```
┌─────────────────────────┐
│  ◄  TASK DETAIL    ✓   │
│ ─────────────────────── │
│  Review contract        │
│  Sheet: Work            │
│  Due:   Jun 5, 2026     │
│  Status: Pending        │
│  Remarks: Check clause  │
│           3 and 7       │
│ ─────────────────────── │
│ [OK] Mark Done          │
│ [▼]  Delete             │
└─────────────────────────┘
```

### Screen 5 — Listening / Processing
```
┌─────────────────────────┐
│                         │
│        ◉  ◉             │  ← wide eyes
│          ○              │  ← open mouth
│                         │
│   ████████░░░░░░░░░     │  ← audio level bar
│                         │
│     "Listening..."      │
│                         │
└─────────────────────────┘
```

### Screen 6 — WiFi Setup
```
┌─────────────────────────┐
│  ◄  WIFI SETUP     ✓   │
│ ─────────────────────── │
│  Scan Results:          │
│ ► 📶 HomeNetwork  ████  │
│   📶 Office_WiFi  ███░  │
│   📶 iPhone_AP    ██░░  │
│ ─────────────────────── │
│ [OK] Connect            │
│ Password: via voice 🎤  │
└─────────────────────────┘
```
*WiFi password entered by voice — you say it, Whisper transcribes, no keyboard needed*

### Screen 7 — Pomodoro
```
┌─────────────────────────┐
│  ◄  POMODORO            │
│ ─────────────────────── │
│                         │
│       25:00             │  ← countdown
│    ████████████░░░      │  ← progress bar
│                         │
│  Task: Review contract  │
│  Session: 2 of 4        │
│                         │
│  [OK] Pause  [▼] Stop   │
└─────────────────────────┘
```

### Screen 8 — Response Text
```
┌─────────────────────────┐
│                         │
│        ◕  ◉             │  ← winking face
│          ◡              │
│                         │
│  "Added! Meeting with   │
│   Rahul on Monday 3pm   │
│   in Work sheet.        │
│   Reminder set ✓"       │
│                         │
└─────────────────────────┘
```

---

## 🛒 Complete Bill of Materials

### CORE ELECTRONICS

| # | Component | Model / Spec | Qty | Est. Cost |
|---|-----------|-------------|-----|-----------|
| 1 | Microcontroller | ESP32 DevKit v1 (38-pin, ESP-WROOM-32) | 1 | $5–8 |
| 2 | Display | 3.5" ILI9486 SPI TFT (320×480) — **NOT XPT2046 touch, get SPI-only version** | 1 | $8–12 |
| 3 | Microphone | INMP441 I2S MEMS Microphone | 1 | $2–4 |
| 4 | Speaker Amp | MAX98357A I2S 3W Amplifier breakout | 1 | $2–4 |
| 5 | Speaker | 40mm 4Ω or 8Ω 3W speaker | 1 | $1–3 |

> **Display note:** Your existing RPi 3.5" display (XPT2046) is meant for RPi GPIO header — it won't directly plug into ESP32. Get a **standard 3.5" SPI TFT module** (ILI9486 or ILI9341) for ESP32. These are cheap and use the same SPI wiring.

---

### BUTTONS & INPUT

| # | Component | Spec | Qty | Est. Cost |
|---|-----------|------|-----|-----------|
| 6 | Tactile push buttons | 12×12mm PCB mount, momentary | 5 | $0.50 |
| 7 | Button caps | Colored caps for tactile buttons (nav = grey, MIC = red) | 5 | $0.50 |
| 8 | Pull-down resistors | 10kΩ (for buttons, if not using internal pull-up) | 5 | $0.10 |

---

### POWER SYSTEM

| # | Component | Spec | Qty | Est. Cost |
|---|-----------|------|-----|-----------|
| 9 | Li-Po Battery | 3.7V 3000–4000mAh with protection circuit | 1 | $5–8 |
| 10 | Charge module | TP4056 USB-C charging module with protection | 1 | $0.80 |
| 11 | Boost converter | MT3608 or IP5306 (3.7V → 5V, 2A) | 1 | $1–2 |
| 12 | Power switch | SPDT slide switch or rocker switch | 1 | $0.50 |
| 13 | Decoupling capacitors | 100µF + 10µF electrolytic (audio noise filtering) | 2 | $0.30 |
| 14 | LED indicator | 3mm LED (green=charging, blue=on) + 220Ω resistor | 2 | $0.20 |

> **Tip:** The **IP5306** is a single chip that does charge + boost + LED indicators — cleaner than TP4056 + MT3608 combo. Used in many power banks.

---

### ENCLOSURE & MECHANICAL

| # | Component | Spec | Qty | Est. Cost |
|---|-----------|------|-----|-----------|
| 15 | Enclosure | 3D printed custom (STL provided) OR project box ~100×60×25mm | 1 | $2–5 |
| 16 | M2 screws | M2×6mm self-tapping for PCB/display mount | 8 | $0.50 |
| 17 | Display bezel | 3D printed or cut from acrylic | 1 | $1 |
| 18 | Speaker grille | Mesh fabric or 3D printed grill | 1 | $0.50 |
| 19 | Rubber feet | 3mm self-adhesive | 4 | $0.30 |

---

### CONNECTIVITY & WIRING

| # | Component | Spec | Qty | Est. Cost |
|---|-----------|------|-----|-----------|
| 20 | PCB | Custom 70×50mm PCB (JLCPCB) OR perfboard | 1 | $2–5 |
| 21 | Pin headers | 2.54mm male + female headers | 2 strips | $0.50 |
| 22 | JST connector | JST PH 2-pin for battery | 1 | $0.30 |
| 23 | USB-C breakout | For charging port on enclosure | 1 | $0.80 |
| 24 | Ribbon cable / jumpers | 20cm female-female dupont for prototyping | 20 | $0.50 |

---

### RASPBERRY PI 5 SERVER UPGRADES

| # | Component | Spec | Qty | Est. Cost |
|---|-----------|------|-----|-----------|
| 25 | M.2 NVMe HAT | Official Pi5 M.2 HAT+ | 1 | $12–15 |
| 26 | NVMe SSD | 256GB M.2 2242 NVMe (WD/Kingston) | 1 | $20–25 |
| 27 | Active cooler | Official Pi5 Active Cooler (fan + heatsink) | 1 | $5–8 |
| 28 | Pi5 power supply | 27W USB-C PD supply (official) | 1 | $12 |
| 29 | Ethernet cable | Cat5e for stable server connection | 1 | $2 |

---

### OPTIONAL / NICE TO HAVE

| # | Component | Use | Est. Cost |
|---|-----------|-----|-----------|
| 30 | Vibration motor | Haptic feedback on button press | $1 |
| 31 | RGB LED (WS2812) | Status indicator ring (listening/thinking/error) | $1 |
| 32 | Buzzer (passive) | Beep on wake word, confirm actions | $0.50 |
| 33 | RTC module (DS3231) | Keep time without WiFi | $2 |
| 34 | SD card slot breakout | Store TTS cache, audio clips | $1 |
| 35 | UPS HAT for Pi5 | Keep server running during power cuts | $20 |

---

## 💰 Cost Summary

| Category | Est. Cost |
|----------|-----------|
| ESP32 + Core electronics | $18–31 |
| Buttons & input | ~$1 |
| Power system | ~$8–12 |
| Enclosure & mechanical | ~$5–8 |
| Connectivity & wiring | ~$5 |
| **ESP32 Device Total** | **~$37–57** |
| Pi5 upgrades (NVMe + cooler + PSU) | ~$50–60 |
| **Grand Total** | **~$87–117** |

---

## 🎮 Button → GPIO Map (ESP32)

```
Button      →  ESP32 GPIO   Physical
────────────────────────────────────
BTN BACK    →  GPIO 34      (input only, perfect for button)
BTN UP      →  GPIO 35      (input only)
BTN DOWN    →  GPIO 33
BTN OK      →  GPIO 13
BTN MIC/PTT →  GPIO 14
```
All buttons wired with internal pull-up (`INPUT_PULLUP`), active LOW on press.

---

## 🖥️ Revised Full GPIO Map (ESP32)

```
GPIO  │  Function
──────┼─────────────────────────────
2     │  Display DC
4     │  Display RESET
13    │  BTN OK/SELECT
14    │  BTN MIC/PTT
15    │  Display CS
18    │  SPI CLK (display)
19    │  SPI MISO (display)
22    │  MAX98357A DIN (I2S1 TX)
23    │  SPI MOSI (display)
25    │  I2S LRCK (shared mic+spk)
26    │  INMP441 BCLK (I2S0)
27    │  MAX98357A BCLK (I2S1)
32    │  INMP441 DATA (I2S0 RX)
33    │  BTN DOWN
34    │  BTN BACK  (input only)
35    │  BTN UP    (input only)
```

---

## 📦 What To Order — Quick List

**From AliExpress / Amazon:**
1. ESP32 DevKit v1 × 1
2. 3.5" ILI9486 SPI TFT display (480×320, no touch) × 1
3. INMP441 microphone module × 1
4. MAX98357A amplifier module × 1
5. 40mm 8Ω 3W speaker × 1
6. TP4056 USB-C charging module × 1
7. MT3608 boost converter (5V) × 1 (or IP5306 all-in-one)
8. 3.7V Li-Po 3000mAh × 1
9. 12×12mm tactile push buttons × 5 (pack of 20, $1)
10. SPDT slide switch × 1
11. 100µF + 10µF capacitors × 2 each
12. Dupont jumper wires × pack
13. Perfboard (7×5cm) × 1

**For Pi5:**
14. Official Pi5 M.2 HAT+ × 1
15. 256GB NVMe M.2 2242 SSD × 1
16. Official Pi5 Active Cooler × 1
