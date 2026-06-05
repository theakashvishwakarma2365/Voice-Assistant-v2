#pragma once

// ════════════════════════════════════════════════════════════════
//  VoiceDesk ESP32 — Pin & Hardware Configuration
// ════════════════════════════════════════════════════════════════

// ── Display (ILI9486, 3.5" MPI3501, SPI) ────────────────────
// TFT_eSPI pins defined in User_Setup.h (see below)
// Reminder:  CS=15  DC=2  RST=4  MOSI=23  SCK=18  MISO=19
#define DISPLAY_WIDTH   480
#define DISPLAY_HEIGHT  320
#define DISPLAY_ROTATION 1   // landscape

// ── INMP441 Microphone (I2S port 0) ─────────────────────────
#define MIC_WS   25   // LRCK
#define MIC_SCK  26   // BCLK
#define MIC_SD   32   // data in
#define MIC_PORT I2S_NUM_0
#define MIC_SAMPLE_RATE  16000
#define MIC_BUFFER_SIZE  1024  // samples per DMA buffer

// ── MAX98357A Speaker (I2S port 1) ──────────────────────────
#define SPK_BCLK 27
#define SPK_LRC  25   // shared with mic LRCK
#define SPK_DIN  22
#define SPK_PORT I2S_NUM_1

// ── SD Card (SPI bus, shared with display) ──────────────────
#define SD_CS    5

// ── Buttons (active LOW, INPUT_PULLUP) ──────────────────────
#define BTN_BACK  34   // input-only pin
#define BTN_UP    35   // input-only pin
#define BTN_DOWN  33
#define BTN_OK    13
#define BTN_MIC   14   // PTT / hold to record

#define BTN_LONG_PRESS_MS  800    // long press threshold
#define BTN_DEBOUNCE_MS    50

// ── Network ─────────────────────────────────────────────────
#define SERVER_DEFAULT_HOST  "voicedesk.local"
#define SERVER_PORT          8000
#define WS_PATH              "/ws/audio"
#define WS_RECONNECT_MS      3000
#define WIFI_CONNECT_TIMEOUT 15000

// ── Audio streaming ──────────────────────────────────────────
#define AUDIO_CHUNK_BYTES    512   // PCM bytes per WebSocket frame
#define PTT_SILENCE_MS       800   // stop recording after N ms silence

// ── NVS keys ─────────────────────────────────────────────────
#define NVS_NAMESPACE   "voicedesk"
#define NVS_KEY_SSID    "wifi_ssid"
#define NVS_KEY_PASS    "wifi_pass"
#define NVS_KEY_HOST    "server_host"
#define NVS_KEY_THEME   "theme_id"

// ── SD paths ─────────────────────────────────────────────────
#define SD_ROOT         "/voicedesk"
#define SD_QUEUE_DIR    "/voicedesk/queue"
#define SD_SYNCED_DIR   "/voicedesk/synced"
#define SD_CONFIG_FILE  "/voicedesk/config.json"
