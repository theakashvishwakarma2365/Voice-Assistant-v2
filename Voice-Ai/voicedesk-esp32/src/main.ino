/*
 * VoiceDesk ESP32 Firmware v1.0
 * ─────────────────────────────────────────────────────────────
 * Hardware:
 *   Display  : MPI3501 3.5" ILI9486 SPI (CS=15, DC=2, RST=4)
 *   Mic      : INMP441 I2S (WS=25, SCK=26, SD=32)
 *   Speaker  : MAX98357A I2S (BCLK=27, LRC=25, DIN=22)
 *   SD Card  : SPI shared bus (CS=5)
 *   Buttons  : BACK=34 UP=35 DOWN=33 OK=13 MIC=14
 *
 * Libraries required (install via Library Manager or platformio.ini):
 *   - TFT_eSPI            (configure User_Setup.h — see below)
 *   - ArduinoWebsockets   by Gil Maimon
 *   - ArduinoJson         v7
 *   - SD                  (built-in ESP32)
 *   - Preferences         (built-in ESP32)
 *   - driver/i2s.h        (ESP-IDF, included with ESP32 core)
 * ─────────────────────────────────────────────────────────────
 */

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>
#include <math.h>

#include "config.h"
#include "themes.h"
#include "buttons.h"
#include "audio.h"
#include "storage.h"
#include "network.h"
#include "ui.h"

// ── Global instances ─────────────────────────────────────────
TFT_eSPI tft;
VoiceUI  ui(tft);
ThemeID  activeTheme = THEME_INK;   // defined in themes.h (extern)
char     serverHost[64];

// ── State machine ─────────────────────────────────────────────
enum AppState {
    APP_BOOT,
    APP_WIFI_SETUP,
    APP_CONNECTING,
    APP_HOME,
    APP_MENU,
    APP_TASKS,
    APP_TASK_DETAIL,
    APP_RECORDING,
    APP_PROCESSING,
    APP_SPEAKING,
    APP_POMODORO,
    APP_SETTINGS,
    APP_SYNCING,
    APP_ERROR,
};
static AppState appState = APP_BOOT;

// ── Audio buffers ─────────────────────────────────────────────
static int16_t  micBuf[512];
static uint8_t  wavBuf[64 * 1024];   // 64KB for TTS WAV
static bool     recording    = false;
static uint32_t silenceStart = 0;
static bool     hasSilence   = false;

// ── Timing ────────────────────────────────────────────────────
static uint32_t lastRender  = 0;
static uint32_t lastRecon   = 0;
static uint32_t lastClock   = 0;
static uint32_t lastQueueCheck = 0;

#define RENDER_INTERVAL_MS   33    // ~30fps
#define RECONNECT_INTERVAL_MS 4000
#define CLOCK_INTERVAL_MS    10000
#define QUEUE_CHECK_MS       5000


// ══════════════════════════════════════════════════════════════
//  WEBSOCKET MESSAGE HANDLER
// ══════════════════════════════════════════════════════════════
void onServerMessage(const char* json) {
    StaticJsonDocument<1024> doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) return;

    const char* type = doc["type"] | "";

    if (strcmp(type, "state") == 0) {
        // Server notifying state change
        const char* face = doc["face"] | "";
        if      (strcmp(face, "thinking") == 0) {
            appState = APP_PROCESSING;
            ui.faceState = FACE_THINKING;
        }

    } else if (strcmp(type, "transcript") == 0) {
        // STT result — show what was heard
        strncpy(ui.responseText, doc["text"] | "", 255);

    } else if (strcmp(type, "response") == 0 || strcmp(type, "clarification") == 0) {
        // Full response — play audio, show text
        const char* text     = doc["response_text"] | doc["question"] | "";
        const char* audioFile= doc["audio_file"] | "";

        strncpy(ui.responseText, text, 255);

        // Download and play TTS audio
        if (strlen(audioFile) > 0) {
            size_t wavLen = 0;
            if (http_get_wav(audioFile, wavBuf, sizeof(wavBuf), wavLen)) {
                appState = APP_SPEAKING;
                ui.currentScreen = SCREEN_SPEAKING;
                ui.faceState     = FACE_SPEAKING;
                spk_play_wav(wavBuf, wavLen);
            }
        }
        appState = APP_HOME;
        ui.currentScreen = SCREEN_HOME;
        ui.faceState     = FACE_SUCCESS;
        // Show success face briefly then return to idle
        ui.render();
        delay(1500);
        ui.faceState = FACE_IDLE;

    } else if (strcmp(type, "error") == 0) {
        strncpy(ui.errorText, doc["response_text"] | "Unknown error", 127);
        appState = APP_ERROR;
        ui.currentScreen = SCREEN_ERROR;
        ui.faceState     = FACE_ERROR;

    } else if (strcmp(type, "reminder") == 0) {
        // Reminder notification from server
        strncpy(ui.responseText, doc["message"] | "Reminder!", 255);
        ui.currentScreen = SCREEN_SPEAKING;
        appState = APP_SPEAKING;

    } else if (strcmp(type, "pong") == 0) {
        // keepalive OK

    } else if (strcmp(type, "sync_ack") == 0) {
        appState = APP_HOME;
        ui.currentScreen = SCREEN_HOME;
        strcpy(ui.subText, "Sync complete!");
    }
}

void onServerConnect() {
    ui.status.serverOk = true;
    strcpy(ui.subText, "");
    // Flush offline queue
    if (ui.status.pendingQueue > 0) {
        appState = APP_SYNCING;
        ui.currentScreen = SCREEN_SYNCING;
        strcpy(ui.subText, "Flushing offline queue...");
        sd_queue_flush([](const char* type, const char* payload) -> bool {
            return http_post_offline(type, payload);
        });
        ui.status.pendingQueue = sd_queue_count();
        appState = APP_HOME;
        ui.currentScreen = SCREEN_HOME;
    }
}

void onServerDisconnect() {
    ui.status.serverOk = false;
}


// ══════════════════════════════════════════════════════════════
//  BUTTON HANDLERS
// ══════════════════════════════════════════════════════════════
void handle_buttons() {
    ButtonEvent evBack = buttons_poll(BTN_ID_BACK);
    ButtonEvent evUp   = buttons_poll(BTN_ID_UP);
    ButtonEvent evDown = buttons_poll(BTN_ID_DOWN);
    ButtonEvent evOk   = buttons_poll(BTN_ID_OK);
    ButtonEvent evMic  = buttons_poll(BTN_ID_MIC);

    // ── MIC button: hold to record ────────────────────────────
    bool micHeld = buttons_is_held(BTN_ID_MIC);
    if (micHeld && !recording && ws_is_connected()) {
        recording    = true;
        silenceStart = 0;
        hasSilence   = false;
        appState     = APP_RECORDING;
        ui.currentScreen = SCREEN_LISTENING;
        ui.faceState     = FACE_LISTENING;
    } else if (!micHeld && recording) {
        // Released — send end marker
        recording = false;
        ws_send_audio_end();
        appState = APP_PROCESSING;
        ui.currentScreen = SCREEN_THINKING;
        ui.faceState     = FACE_THINKING;
    }

    if (evMic == LONG_PRESS) {
        // Toggle always-listen mode (future)
    }

    // ── Navigation by screen ──────────────────────────────────
    switch (appState) {

        case APP_HOME:
            if (evBack == SHORT_PRESS || evOk == SHORT_PRESS) {
                appState = APP_MENU;
                ui.currentScreen = SCREEN_MENU;
                ui.menuSel = 0;
            }
            if (evOk == LONG_PRESS) {
                appState = APP_MENU;
                ui.currentScreen = SCREEN_MENU;
            }
            break;

        case APP_MENU:
            if (evUp   == SHORT_PRESS) ui.menuSel = max(0, ui.menuSel - 1);
            if (evDown == SHORT_PRESS) ui.menuSel = min(MENU_COUNT - 1, ui.menuSel + 1);
            if (evOk   == SHORT_PRESS) {
                // Navigate to selected menu item
                switch (ui.menuSel) {
                    case 0: // Tasks
                        appState = APP_TASKS;
                        ui.currentScreen = SCREEN_TASK_LIST;
                        ui.listSel = 0; ui.listTop = 0;
                        http_get_tasks(&ui);
                        break;
                    case 4: // Settings
                        appState = APP_SETTINGS;
                        ui.currentScreen = SCREEN_SETTINGS;
                        ui.settingsSel = (uint8_t)activeTheme;
                        break;
                    case 5: // WiFi
                        appState = APP_WIFI_SETUP;
                        ui.currentScreen = SCREEN_WIFI_SETUP;
                        ui.netCount = wifi_scan(ui.nets, VoiceUI::MAX_NETS);
                        break;
                    default:
                        appState = APP_TASKS;
                        ui.currentScreen = SCREEN_TASK_LIST;
                        break;
                }
            }
            if (evBack == SHORT_PRESS || evBack == LONG_PRESS) {
                appState = APP_HOME;
                ui.currentScreen = SCREEN_HOME;
            }
            break;

        case APP_TASKS:
            if (evUp   == SHORT_PRESS) {
                if (ui.listSel > 0) {
                    ui.listSel--;
                    if (ui.listSel < ui.listTop) ui.listTop--;
                }
            }
            if (evDown == SHORT_PRESS) {
                if (ui.listSel < ui.taskCount - 1) {
                    ui.listSel++;
                    uint8_t visible = (DISPLAY_HEIGHT - 60) / 36;
                    if (ui.listSel >= ui.listTop + visible) ui.listTop++;
                }
            }
            if (evOk == SHORT_PRESS) {
                appState = APP_TASK_DETAIL;
                ui.currentScreen = SCREEN_TASK_DETAIL;
            }
            if (evBack == SHORT_PRESS) {
                appState = APP_MENU;
                ui.currentScreen = SCREEN_MENU;
            }
            break;

        case APP_TASK_DETAIL:
            if (evBack == SHORT_PRESS) {
                appState = APP_TASKS;
                ui.currentScreen = SCREEN_TASK_LIST;
            }
            if (evOk == SHORT_PRESS) {
                // Send "mark done" command via WebSocket
                StaticJsonDocument<128> doc;
                doc["type"]   = "command";
                doc["text"]   = String("mark done ") + ui.tasks[ui.listSel].title;
                char buf[200];
                serializeJson(doc, buf, 200);
                ws_send_json(buf);
            }
            break;

        case APP_SETTINGS:
            if (evUp == SHORT_PRESS || evBack == SHORT_PRESS && false) {
                // LEFT = previous theme
                if (ui.settingsSel > 0) ui.settingsSel--;
            }
            if (evDown == SHORT_PRESS) {
                // RIGHT = next theme
                if (ui.settingsSel < THEME_COUNT - 1) ui.settingsSel++;
            }
            if (evOk == SHORT_PRESS) {
                // Apply theme
                activeTheme = (ThemeID)ui.settingsSel;
                nvs_set_int(NVS_KEY_THEME, (int)activeTheme);
            }
            if (evBack == SHORT_PRESS) {
                appState = APP_MENU;
                ui.currentScreen = SCREEN_MENU;
            }
            break;

        case APP_WIFI_SETUP:
            if (evUp   == SHORT_PRESS && ui.netSel > 0) ui.netSel--;
            if (evDown == SHORT_PRESS && ui.netSel < ui.netCount - 1) ui.netSel++;
            if (evOk   == SHORT_PRESS) {
                // Prompt for password via voice
                ui.currentScreen = SCREEN_LISTENING;
                strcpy(ui.subText, "Say your WiFi password...");
                // (WiFi password capture via STT handled in next voice round)
            }
            if (evBack == SHORT_PRESS) {
                appState = APP_MENU;
                ui.currentScreen = SCREEN_MENU;
            }
            break;

        case APP_POMODORO:
            if (evOk   == SHORT_PRESS) { /* pause */ }
            if (evDown == SHORT_PRESS) {
                ui.pomodoroEndMs = 0; // stop
                appState = APP_HOME;
                ui.currentScreen = SCREEN_HOME;
            }
            if (evBack == SHORT_PRESS) {
                appState = APP_HOME;
                ui.currentScreen = SCREEN_HOME;
            }
            // Pomodoro finished?
            if (ui.pomodoroEndMs > 0 && millis() >= ui.pomodoroEndMs) {
                ui.pomodoroEndMs = 0;
                // Play bell (synthesise short beep pattern)
                int16_t beep[4410]; // 0.2s at 22050Hz
                for (int i = 0; i < 4410; i++)
                    beep[i] = (int16_t)(8000 * sin(2 * PI * 880 * i / 22050.0f));
                for (int r = 0; r < 3; r++) {
                    spk_play_pcm(beep, 4410);
                    delay(200);
                }
                strcpy(ui.responseText, "Pomodoro done! Great focus.");
                appState = APP_SPEAKING;
                ui.currentScreen = SCREEN_SPEAKING;
            }
            break;

        case APP_ERROR:
            if (evOk   == SHORT_PRESS) ws_connect(); // retry
            if (evBack == SHORT_PRESS) {
                appState = APP_HOME;
                ui.currentScreen = SCREEN_HOME;
                ui.faceState = FACE_IDLE;
            }
            break;

        case APP_SPEAKING:
            if (evOk == SHORT_PRESS || evBack == SHORT_PRESS) {
                spk_stop();
                appState = APP_HOME;
                ui.currentScreen = SCREEN_HOME;
            }
            break;

        default: break;
    }
}


// ══════════════════════════════════════════════════════════════
//  AUDIO RECORDING LOOP
// ══════════════════════════════════════════════════════════════
void handle_recording() {
    if (!recording) return;

    size_t bytes = mic_read(micBuf, 512);
    ui.audioLevel = mic_level(micBuf, bytes / 2);

    // Stream PCM to server
    ws_send_audio((const uint8_t*)micBuf, bytes);

    // Auto-stop on silence
    if (mic_is_silent(micBuf, bytes / 2)) {
        if (!hasSilence) { silenceStart = millis(); hasSilence = true; }
        else if (millis() - silenceStart > PTT_SILENCE_MS) {
            recording = false;
            ws_send_audio_end();
            appState = APP_PROCESSING;
            ui.currentScreen = SCREEN_THINKING;
            ui.faceState     = FACE_THINKING;
        }
    } else {
        hasSilence = false;
    }
}


// ══════════════════════════════════════════════════════════════
//  SETUP
// ══════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(115200);
    Serial.println("\n\n╔══════════════════════════╗");
    Serial.println(  "║  VoiceDesk ESP32 v1.0    ║");
    Serial.println(  "╚══════════════════════════╝");

    // ── NVS (load saved config) ───────────────────────────────
    nvs_init();
    activeTheme = (ThemeID)nvs_get_int(NVS_KEY_THEME, THEME_INK);
    String savedHost = nvs_get(NVS_KEY_HOST, SERVER_DEFAULT_HOST);
    strncpy(serverHost, savedHost.c_str(), 63);

    // ── Display ───────────────────────────────────────────────
    ui.begin();
    ui.currentScreen = SCREEN_HOME;
    ui.faceState     = FACE_IDLE;

    // Boot splash
    ui.sprMain.fillSprite(T().bg);
    ui.sprMain.setTextColor(T().text, T().bg);
    ui.sprMain.setTextDatum(MC_DATUM);
    ui.sprMain.setTextSize(3);
    ui.sprMain.drawString("VoiceDesk", DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2 - 20);
    ui.sprMain.setTextSize(1);
    ui.sprMain.setTextColor(T().textDim, T().bg);
    ui.sprMain.drawString("Starting up...", DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2 + 20);
    ui.sprMain.pushSprite(0, 0);

    // ── Buttons ───────────────────────────────────────────────
    buttons_init();

    // ── SD card ───────────────────────────────────────────────
    ui.status.sdOk = sd_init();
    ui.status.pendingQueue = sd_queue_count();

    // ── Audio ─────────────────────────────────────────────────
    mic_init();
    spk_init();

    // ── WiFi ──────────────────────────────────────────────────
    String ssid = nvs_get(NVS_KEY_SSID);
    String pass = nvs_get(NVS_KEY_PASS);

    if (ssid.length() > 0) {
        ui.sprMain.fillSprite(T().bg);
        ui.sprMain.setTextDatum(MC_DATUM);
        ui.sprMain.setTextColor(T().textDim, T().bg);
        ui.sprMain.setTextSize(1);
        ui.sprMain.drawString(String("Connecting to ") + ssid, DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2);
        ui.sprMain.pushSprite(0, 0);

        ui.status.wifiOk = wifi_connect(ssid.c_str(), pass.c_str());
    } else {
        // First boot — go to WiFi setup
        appState = APP_WIFI_SETUP;
        ui.currentScreen = SCREEN_WIFI_SETUP;
        ui.netCount = wifi_scan(ui.nets, VoiceUI::MAX_NETS);
    }

    // ── WebSocket ─────────────────────────────────────────────
    if (ui.status.wifiOk) {
        ws_set_callbacks(onServerMessage, onServerConnect, onServerDisconnect);
        ws_connect();
    }

    appState = APP_HOME;
    Serial.println("[Boot] Ready");
}


// ══════════════════════════════════════════════════════════════
//  LOOP
// ══════════════════════════════════════════════════════════════
void loop() {
    uint32_t now = millis();

    // ── WebSocket poll ────────────────────────────────────────
    ws_loop();

    // ── Button handling ───────────────────────────────────────
    handle_buttons();

    // ── Audio recording ───────────────────────────────────────
    handle_recording();

    // ── Auto-reconnect WebSocket ──────────────────────────────
    if (ui.status.wifiOk && !ws_is_connected() && (now - lastRecon) > RECONNECT_INTERVAL_MS) {
        lastRecon = now;
        ws_connect();
    }

    // ── Periodic queue count refresh ─────────────────────────
    if ((now - lastQueueCheck) > QUEUE_CHECK_MS) {
        lastQueueCheck = now;
        ui.status.pendingQueue = sd_queue_count();
    }

    // ── Clock update (simple counter) ────────────────────────
    if ((now - lastClock) > CLOCK_INTERVAL_MS) {
        lastClock = now;
        // Basic uptime clock (replace with NTP for real time)
        uint32_t secs  = now / 1000;
        uint32_t hours = (secs / 3600) % 24;
        uint32_t mins  = (secs / 60)   % 60;
        snprintf(ui.status.timeStr, 6, "%02lu:%02lu", hours, mins);
    }

    // ── Render (throttled) ───────────────────────────────────
    if ((now - lastRender) >= RENDER_INTERVAL_MS) {
        lastRender = now;
        ui.render();
    }
}
