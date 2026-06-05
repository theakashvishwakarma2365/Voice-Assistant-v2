#pragma once
#include <TFT_eSPI.h>
#include "themes.h"
#include "config.h"

// ════════════════════════════════════════════════════════════════
//  UI renderer — all drawing goes through here
//  Uses TFT_eSPI sprites for flicker-free double-buffered render
// ════════════════════════════════════════════════════════════════

// ── Screen IDs ───────────────────────────────────────────────
enum ScreenID {
    SCREEN_HOME = 0,
    SCREEN_MENU,
    SCREEN_TASK_LIST,
    SCREEN_TASK_DETAIL,
    SCREEN_LISTENING,
    SCREEN_THINKING,
    SCREEN_SPEAKING,
    SCREEN_RESPONSE,
    SCREEN_POMODORO,
    SCREEN_WIFI_SETUP,
    SCREEN_SETTINGS,
    SCREEN_ERROR,
    SCREEN_SYNCING,
};

// ── Face states ───────────────────────────────────────────────
enum FaceState {
    FACE_IDLE = 0,
    FACE_LISTENING,
    FACE_THINKING,
    FACE_SPEAKING,
    FACE_SUCCESS,
    FACE_ERROR,
};

// ── Menu items ────────────────────────────────────────────────
struct MenuItem {
    const char* icon;
    const char* label;
    ScreenID    target;
};

static const MenuItem MENU_ITEMS[] = {
    { "T",  "Tasks",    SCREEN_TASK_LIST  },
    { "M",  "Meetings", SCREEN_TASK_LIST  },
    { "P",  "Projects", SCREEN_TASK_LIST  },
    { "Z",  "Pomodoro", SCREEN_POMODORO   },
    { "S",  "Settings", SCREEN_SETTINGS   },
    { "W",  "WiFi",     SCREEN_WIFI_SETUP },
};
static const uint8_t MENU_COUNT = 6;

// ── Status bar state ─────────────────────────────────────────
struct StatusState {
    bool   wifiOk;
    bool   serverOk;
    bool   sheetsOk;
    uint8_t pendingQueue;   // items on SD queue
    bool   sdOk;
    char   timeStr[6];      // "HH:MM"
};

class VoiceUI {
public:
    TFT_eSPI&   tft;
    TFT_eSprite sprMain;    // full-screen sprite (double buffer)
    TFT_eSprite sprFace;    // 120x120 face sprite

    ScreenID    currentScreen = SCREEN_HOME;
    FaceState   faceState     = FACE_IDLE;

    StatusState status = {};

    // Scrollable list state
    int8_t  menuSel  = 0;
    int8_t  listSel  = 0;
    int8_t  listTop  = 0;   // scroll offset

    // Dynamic text
    char    responseText[256] = {};
    char    errorText[128]    = {};
    char    subText[128]      = {};   // sub-line on home

    // Pomodoro
    uint32_t pomodoroEndMs   = 0;
    uint8_t  pomodoroSession = 1;
    char     pomodoroTask[64] = "Focus";

    // Audio level (0-100) for listening bar
    uint8_t  audioLevel = 0;

    // Animation frame counter
    uint32_t animFrame = 0;

    // ── Init ──────────────────────────────────────────────────
    VoiceUI(TFT_eSPI& t) : tft(t), sprMain(&t), sprFace(&t) {}

    void begin() {
        tft.init();
        tft.setRotation(DISPLAY_ROTATION);
        tft.fillScreen(T().bg);

        // Full-screen sprite
        sprMain.setColorDepth(16);
        sprMain.createSprite(DISPLAY_WIDTH, DISPLAY_HEIGHT);

        // Face sprite
        sprFace.setColorDepth(16);
        sprFace.createSprite(120, 120);
    }

    // ── Theme switching ───────────────────────────────────────
    void setTheme(ThemeID id) {
        activeTheme = id;
        render();
    }

    // ── Main render dispatcher ────────────────────────────────
    void render() {
        sprMain.fillSprite(T().bg);
        drawStatusBar();
        switch (currentScreen) {
            case SCREEN_HOME:       drawHome();       break;
            case SCREEN_MENU:       drawMenu();       break;
            case SCREEN_TASK_LIST:  drawTaskList();   break;
            case SCREEN_TASK_DETAIL:drawTaskDetail(); break;
            case SCREEN_LISTENING:  drawListening();  break;
            case SCREEN_THINKING:   drawThinking();   break;
            case SCREEN_SPEAKING:   drawSpeaking();   break;
            case SCREEN_POMODORO:   drawPomodoro();   break;
            case SCREEN_WIFI_SETUP: drawWifiSetup();  break;
            case SCREEN_SETTINGS:   drawSettings();   break;
            case SCREEN_ERROR:      drawError();      break;
            case SCREEN_SYNCING:    drawSyncing();    break;
            default: drawHome(); break;
        }
        sprMain.pushSprite(0, 0);
        animFrame++;
    }

    // ══════════════════════════════════════════════════════════
    //  STATUS BAR  (always-on, 20px top strip)
    // ══════════════════════════════════════════════════════════
    void drawStatusBar() {
        sprMain.fillRect(0, 0, DISPLAY_WIDTH, 20, T().statusBar);
        sprMain.setTextColor(T().statusText, T().statusBar);
        sprMain.setTextSize(1);
        sprMain.setTextDatum(ML_DATUM);

        // Left: theme name
        sprMain.drawString(T().name, 6, 10);

        // Centre: time
        sprMain.setTextDatum(MC_DATUM);
        sprMain.drawString(status.timeStr, DISPLAY_WIDTH / 2, 10);

        // Right: icons
        int x = DISPLAY_WIDTH - 6;
        sprMain.setTextDatum(MR_DATUM);

        // WiFi icon
        uint16_t wifiCol = status.wifiOk ? T().ok : T().err;
        sprMain.setTextColor(wifiCol, T().statusBar);
        sprMain.drawString(status.wifiOk ? "W" : "w", x, 10); x -= 14;

        // Server icon
        uint16_t srvCol = status.serverOk ? T().ok : T().err;
        sprMain.setTextColor(srvCol, T().statusBar);
        sprMain.drawString(status.serverOk ? "S" : "s", x, 10); x -= 14;

        // SD / queue icon
        if (!status.sdOk) {
            sprMain.setTextColor(T().warn, T().statusBar);
            sprMain.drawString("X", x, 10); x -= 14;
        } else if (status.pendingQueue > 0) {
            sprMain.setTextColor(T().warn, T().statusBar);
            char buf[8]; snprintf(buf, 8, "%d", status.pendingQueue);
            sprMain.drawString(buf, x, 10); x -= 14;
        }

        // Divider line
        sprMain.drawFastHLine(0, 20, DISPLAY_WIDTH, T().border);
    }

    // ══════════════════════════════════════════════════════════
    //  HOME SCREEN — animated ink face
    // ══════════════════════════════════════════════════════════
    void drawHome() {
        int cx = DISPLAY_WIDTH / 2;
        int cy = (DISPLAY_HEIGHT + 20) / 2;

        // Face circle (ink style: just outline, no heavy fill)
        if (activeTheme == THEME_INK) {
            sprMain.fillCircle(cx, cy, 62, T().faceBg);
            sprMain.drawCircle(cx, cy, 62, T().border);
            sprMain.drawCircle(cx, cy, 61, T().border);
        } else {
            sprMain.fillCircle(cx, cy, 62, T().faceBg);
            sprMain.drawCircle(cx, cy, 62, T().accent);
        }

        drawFaceOnSprite(sprMain, cx, cy);

        // Subtitle text
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(BC_DATUM);
        sprMain.setTextSize(1);
        if (strlen(subText) > 0) {
            sprMain.drawString(subText, cx, DISPLAY_HEIGHT - 6);
        } else {
            sprMain.drawString("Hold MIC to speak", cx, DISPLAY_HEIGHT - 6);
        }
    }

    // ══════════════════════════════════════════════════════════
    //  FACE DRAWING (on any sprite)
    // ══════════════════════════════════════════════════════════
    void drawFaceOnSprite(TFT_eSprite& spr, int cx, int cy) {
        bool blinkOn = (animFrame % 60 < 4) && (faceState == FACE_IDLE);

        switch (faceState) {

            case FACE_IDLE: {
                // Eyes — rounded rect (ink style) or filled circle
                if (blinkOn) {
                    // Blink: thin horizontal line
                    spr.drawFastHLine(cx - 22, cy - 14, 14, T().faceEye);
                    spr.drawFastHLine(cx + 8,  cy - 14, 14, T().faceEye);
                } else {
                    _drawEye(spr, cx - 15, cy - 14, 7, false);
                    _drawEye(spr, cx + 15, cy - 14, 7, false);
                }
                // Mouth — gentle curve
                _drawSmile(spr, cx, cy + 12, 18, 6, T().faceMouth);
                break;
            }

            case FACE_LISTENING: {
                // Wide open eyes
                _drawEye(spr, cx - 15, cy - 14, 9, false);
                _drawEye(spr, cx + 15, cy - 14, 9, false);
                // Open mouth circle — animates with audio level
                uint8_t mouthR = 6 + (audioLevel / 20);
                spr.drawCircle(cx, cy + 16, mouthR, T().faceMouth);
                break;
            }

            case FACE_THINKING: {
                // Squinting eyes (half circles)
                _drawEye(spr, cx - 15, cy - 14, 7, true); // squint
                _drawEye(spr, cx + 15, cy - 14, 7, true);
                // Animated dots
                uint8_t dotOn = (animFrame / 15) % 4;
                for (uint8_t d = 0; d < 3; d++) {
                    uint16_t dc = (d < dotOn) ? T().faceMouth : T().border;
                    spr.fillCircle(cx - 12 + d * 12, cy + 18, 3, dc);
                }
                break;
            }

            case FACE_SPEAKING: {
                // Happy eyes
                _drawEye(spr, cx - 15, cy - 14, 7, false);
                _drawEye(spr, cx + 15, cy - 14, 7, false);
                // Mouth bounces with animation frame
                uint8_t mouthH = 4 + (uint8_t)(3.0f * abs(sin(animFrame * 0.25f)));
                spr.fillRoundRect(cx - 14, cy + 10, 28, mouthH + 4, 3, T().faceMouth);
                spr.fillRoundRect(cx - 12, cy + 12, 24, mouthH,     2, T().faceBg);
                break;
            }

            case FACE_SUCCESS: {
                // Wink: one normal eye, one closed
                _drawEye(spr, cx - 15, cy - 14, 8, false);
                spr.drawFastHLine(cx + 8, cy - 14, 14, T().faceEye); // wink
                // Big smile
                _drawSmile(spr, cx, cy + 10, 22, 10, T().faceMouth);
                break;
            }

            case FACE_ERROR: {
                // Worried eyes (angled)
                spr.fillTriangle(cx-24, cy-8, cx-8, cy-20, cx-6, cy-8, T().faceEye);
                spr.fillTriangle(cx+24, cy-8, cx+8, cy-20, cx+6, cy-8, T().faceEye);
                // Frown
                _drawSmile(spr, cx, cy + 22, 18, -6, T().err);
                break;
            }
        }
    }

    // ══════════════════════════════════════════════════════════
    //  MENU SCREEN
    // ══════════════════════════════════════════════════════════
    void drawMenu() {
        // Title
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("MENU", 10, 28);
        sprMain.drawFastHLine(0, 48, DISPLAY_WIDTH, T().border);

        int itemH = 38;
        int startY = 52;
        for (uint8_t i = 0; i < MENU_COUNT; i++) {
            int y = startY + i * itemH;
            bool sel = (i == menuSel);

            // Row background
            if (sel) {
                sprMain.fillRoundRect(4, y, DISPLAY_WIDTH - 8, itemH - 2, 4, T().highlight);
                if (activeTheme == THEME_INK) {
                    sprMain.drawRoundRect(4, y, DISPLAY_WIDTH - 8, itemH - 2, 4, T().accent);
                }
            }

            // Selector marker
            if (sel) {
                sprMain.fillTriangle(8, y + itemH/2 - 5,
                                     8, y + itemH/2 + 5,
                                     16, y + itemH/2, T().accent);
            }

            // Icon box (ink: outlined square, dark: filled)
            uint16_t iconBg = sel ? T().accent : T().bg2;
            uint16_t iconFg = sel ? T().textInvert : T().accent;
            sprMain.fillRoundRect(20, y + 4, 28, 28, 3, iconBg);
            if (activeTheme == THEME_INK)
                sprMain.drawRoundRect(20, y + 4, 28, 28, 3, T().border);
            sprMain.setTextColor(iconFg, iconBg);
            sprMain.setTextDatum(MC_DATUM);
            sprMain.setTextSize(2);
            sprMain.drawString(MENU_ITEMS[i].icon, 34, y + 18);

            // Label
            sprMain.setTextColor(sel ? T().text : T().textDim, T().bg);
            sprMain.setTextDatum(ML_DATUM);
            sprMain.setTextSize(sel ? 2 : 1);
            sprMain.drawString(MENU_ITEMS[i].label, 56, y + 18);

            // Chevron
            if (sel) {
                sprMain.setTextColor(T().accentDim, T().bg);
                sprMain.setTextDatum(MR_DATUM);
                sprMain.setTextSize(2);
                sprMain.drawString(">", DISPLAY_WIDTH - 12, y + 18);
            }

            // Divider (ink only)
            if (activeTheme == THEME_INK && i < MENU_COUNT - 1)
                sprMain.drawFastHLine(8, y + itemH - 1, DISPLAY_WIDTH - 16, T().border);
        }

        _drawNavHint("OK=Select  BACK=Home");
    }

    // ══════════════════════════════════════════════════════════
    //  TASK LIST
    // ══════════════════════════════════════════════════════════

    // Task display struct (filled from JSON response)
    struct TaskItem {
        char title[80];
        char status[16];
        char due[20];
        char sheet[32];
    };
    static const uint8_t MAX_TASKS = 8;
    TaskItem tasks[MAX_TASKS];
    uint8_t  taskCount = 0;

    void drawTaskList() {
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(1);

        // Header
        sprMain.setTextSize(2);
        sprMain.drawString("TASKS", 10, 28);
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextSize(1);
        char cntBuf[20];
        snprintf(cntBuf, 20, "%d items", taskCount);
        sprMain.drawString(cntBuf, 90, 34);
        sprMain.drawFastHLine(0, 48, DISPLAY_WIDTH, T().border);

        if (taskCount == 0) {
            sprMain.setTextColor(T().textDim, T().bg);
            sprMain.setTextDatum(MC_DATUM);
            sprMain.setTextSize(1);
            sprMain.drawString("No tasks. Say 'add a task'.", DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2);
            return;
        }

        int itemH = 36;
        int startY = 52;
        uint8_t visible = (DISPLAY_HEIGHT - 60) / itemH;

        for (uint8_t i = 0; i < visible && (i + listTop) < taskCount; i++) {
            uint8_t idx = i + listTop;
            int y = startY + i * itemH;
            bool sel = (idx == listSel);
            auto& task = tasks[idx];

            if (sel) {
                sprMain.fillRoundRect(4, y, DISPLAY_WIDTH - 8, itemH - 2, 3, T().highlight);
                if (activeTheme == THEME_INK)
                    sprMain.drawRoundRect(4, y, DISPLAY_WIDTH - 8, itemH - 2, 3, T().accent);
            }

            // Status dot
            uint16_t dotCol = T().textDim;
            if      (strcmp(task.status, "done")        == 0) dotCol = T().ok;
            else if (strcmp(task.status, "in_progress") == 0) dotCol = T().warn;
            else if (strcmp(task.status, "pending")     == 0) dotCol = T().accent;
            sprMain.fillCircle(18, y + itemH/2, 5, dotCol);
            if (activeTheme == THEME_INK)
                sprMain.drawCircle(18, y + itemH/2, 5, T().border);

            // Title
            sprMain.setTextColor(sel ? T().text : T().text, T().bg);
            sprMain.setTextDatum(TL_DATUM);
            sprMain.setTextSize(sel ? 2 : 1);
            // Truncate title
            char shortTitle[28];
            strncpy(shortTitle, task.title, 27); shortTitle[27] = 0;
            sprMain.drawString(shortTitle, 30, y + 4);

            // Due date (small)
            if (strlen(task.due) > 0) {
                sprMain.setTextColor(T().textDim, T().bg);
                sprMain.setTextSize(1);
                sprMain.drawString(task.due, 30, y + 22);
            }

            // Sheet badge
            sprMain.setTextColor(T().accentDim, T().bg);
            sprMain.setTextDatum(MR_DATUM);
            sprMain.drawString(task.sheet, DISPLAY_WIDTH - 8, y + itemH/2);

            if (activeTheme == THEME_INK && i < visible - 1)
                sprMain.drawFastHLine(8, y + itemH - 1, DISPLAY_WIDTH - 16, T().border);
        }

        // Scroll indicator
        if (taskCount > visible) {
            int barH = (DISPLAY_HEIGHT - 60) * visible / taskCount;
            int barY = 52 + (DISPLAY_HEIGHT - 60) * listTop / taskCount;
            sprMain.fillRect(DISPLAY_WIDTH - 4, 52, 3, DISPLAY_HEIGHT - 60, T().bg2);
            sprMain.fillRect(DISPLAY_WIDTH - 4, barY, 3, barH, T().accent);
        }

        _drawNavHint("OK=Open  BACK=Menu");
    }

    // ══════════════════════════════════════════════════════════
    //  TASK DETAIL
    // ══════════════════════════════════════════════════════════
    void drawTaskDetail() {
        if (listSel >= taskCount) return;
        auto& task = tasks[listSel];

        sprMain.setTextDatum(TL_DATUM);

        // Title
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextSize(2);
        sprMain.drawString(task.title, 10, 28);
        sprMain.drawFastHLine(0, 50, DISPLAY_WIDTH, T().border);

        // Fields
        int y = 58;
        _drawField("Sheet",  task.sheet,  y); y += 26;
        _drawField("Due",    task.due,    y); y += 26;
        _drawField("Status", task.status, y); y += 26;

        sprMain.drawFastHLine(0, y, DISPLAY_WIDTH, T().border);
        y += 8;

        // Actions
        const char* actions[] = { "Mark Done", "Delete", "Add Remark" };
        for (uint8_t i = 0; i < 3; i++) {
            bool sel = (listSel % 3 == i); // reuse listSel for action select
            uint16_t bg = sel ? T().accent : T().bg2;
            uint16_t fg = sel ? T().textInvert : T().text;
            sprMain.fillRoundRect(10 + i * 154, y, 144, 30, 5, bg);
            if (activeTheme == THEME_INK)
                sprMain.drawRoundRect(10 + i * 154, y, 144, 30, 5, T().border);
            sprMain.setTextColor(fg, bg);
            sprMain.setTextDatum(MC_DATUM);
            sprMain.setTextSize(1);
            sprMain.drawString(actions[i], 10 + i * 154 + 72, y + 15);
        }

        _drawNavHint("OK=Action  BACK=List");
    }

    // ══════════════════════════════════════════════════════════
    //  LISTENING SCREEN
    // ══════════════════════════════════════════════════════════
    void drawListening() {
        int cx = DISPLAY_WIDTH / 2;
        int cy = DISPLAY_HEIGHT / 2 + 10;

        // Pulsing ring (animation)
        uint8_t pulse = (animFrame % 30);
        uint8_t r = 70 + pulse;
        sprMain.drawCircle(cx, cy, r,     T().accentDim);
        sprMain.drawCircle(cx, cy, r + 8, _dimColor(T().accentDim));

        // Face circle
        sprMain.fillCircle(cx, cy, 62, T().faceBg);
        sprMain.drawCircle(cx, cy, 62, T().accent);
        faceState = FACE_LISTENING;
        drawFaceOnSprite(sprMain, cx, cy);

        // Audio level bar
        int barW = (DISPLAY_WIDTH - 60) * audioLevel / 100;
        sprMain.fillRoundRect(30, DISPLAY_HEIGHT - 30, DISPLAY_WIDTH - 60, 10, 5, T().bg2);
        sprMain.fillRoundRect(30, DISPLAY_HEIGHT - 30, barW, 10, 5, T().accent);

        // Label
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TC_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("Listening...", cx, 28);

        _drawNavHint("Release MIC to send");
    }

    // ══════════════════════════════════════════════════════════
    //  THINKING SCREEN
    // ══════════════════════════════════════════════════════════
    void drawThinking() {
        int cx = DISPLAY_WIDTH / 2;
        int cy = DISPLAY_HEIGHT / 2 + 10;

        sprMain.fillCircle(cx, cy, 62, T().faceBg);
        sprMain.drawCircle(cx, cy, 62, T().accentDim);
        faceState = FACE_THINKING;
        drawFaceOnSprite(sprMain, cx, cy);

        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(TC_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("Thinking...", cx, 28);

        // Transcript text (what was heard)
        if (strlen(responseText) > 0) {
            sprMain.setTextColor(T().textDim, T().bg);
            sprMain.setTextDatum(BC_DATUM);
            sprMain.setTextSize(1);
            sprMain.drawString(responseText, cx, DISPLAY_HEIGHT - 6);
        }
    }

    // ══════════════════════════════════════════════════════════
    //  SPEAKING / RESPONSE SCREEN
    // ══════════════════════════════════════════════════════════
    void drawSpeaking() {
        int cx = DISPLAY_WIDTH / 2;
        int faceY = 120;

        sprMain.fillCircle(cx, faceY, 55, T().faceBg);
        sprMain.drawCircle(cx, faceY, 55, T().accent);
        faceState = FACE_SPEAKING;
        drawFaceOnSprite(sprMain, cx, faceY);

        // Response text box
        int boxY = 185;
        int boxH = DISPLAY_HEIGHT - boxY - 25;
        if (activeTheme == THEME_INK) {
            sprMain.fillRoundRect(6, boxY, DISPLAY_WIDTH - 12, boxH, 4, T().bg2);
            sprMain.drawRoundRect(6, boxY, DISPLAY_WIDTH - 12, boxH, 4, T().border);
        } else {
            sprMain.fillRoundRect(6, boxY, DISPLAY_WIDTH - 12, boxH, 4, T().bg2);
        }

        // Word-wrap response text (simple, fixed width)
        sprMain.setTextColor(T().text, T().bg2);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(1);
        _drawWrappedText(responseText, 12, boxY + 6, DISPLAY_WIDTH - 24, boxH - 10);

        _drawNavHint("OK=Done  BACK=Home");
    }

    // ══════════════════════════════════════════════════════════
    //  POMODORO SCREEN
    // ══════════════════════════════════════════════════════════
    void drawPomodoro() {
        int cx = DISPLAY_WIDTH / 2;

        // Task name
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TC_DATUM);
        sprMain.setTextSize(1);
        sprMain.drawString(pomodoroTask, cx, 28);

        // Session badge
        char sessBuf[20];
        snprintf(sessBuf, 20, "Session %d", pomodoroSession);
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.drawString(sessBuf, cx, 42);

        // Time remaining
        uint32_t remaining = (pomodoroEndMs > millis()) ? (pomodoroEndMs - millis()) / 1000 : 0;
        uint32_t totalSec  = 25 * 60;
        char timeBuf[8];
        snprintf(timeBuf, 8, "%02lu:%02lu", remaining / 60, remaining % 60);

        sprMain.setTextColor(T().accent, T().bg);
        sprMain.setTextSize(4);
        sprMain.setTextDatum(MC_DATUM);
        sprMain.drawString(timeBuf, cx, 110);

        // Progress arc (drawn as segmented ring)
        float progress = (totalSec - remaining) / (float)totalSec;
        int arcR = 65;
        int arcX = cx, arcY = 110;
        int segments = 72; // 5-degree segments
        for (int s = 0; s < segments; s++) {
            float angle = (s / (float)segments) * 2 * PI - PI / 2;
            float filled = s < (int)(segments * progress) ? 1.0f : 0.0f;
            uint16_t col = filled ? T().accent : T().bg2;
            int x1 = arcX + (arcR - 4) * cos(angle);
            int y1 = arcY + (arcR - 4) * sin(angle);
            int x2 = arcX + arcR * cos(angle);
            int y2 = arcY + arcR * sin(angle);
            sprMain.drawLine(x1, y1, x2, y2, col);
        }

        sprMain.drawFastHLine(0, 178, DISPLAY_WIDTH, T().border);

        // Buttons hint
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(TC_DATUM);
        sprMain.setTextSize(1);
        sprMain.drawString("OK=Pause  DOWN=Stop  BACK=Home", cx, 186);
    }

    // ══════════════════════════════════════════════════════════
    //  WIFI SETUP SCREEN
    // ══════════════════════════════════════════════════════════

    struct WifiNet {
        char ssid[32];
        int8_t rssi;
    };
    static const uint8_t MAX_NETS = 6;
    WifiNet nets[MAX_NETS];
    uint8_t netCount = 0;
    uint8_t netSel   = 0;

    void drawWifiSetup() {
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("WiFi Setup", 10, 28);
        sprMain.drawFastHLine(0, 48, DISPLAY_WIDTH, T().border);

        if (netCount == 0) {
            sprMain.setTextColor(T().textDim, T().bg);
            sprMain.setTextDatum(MC_DATUM);
            sprMain.setTextSize(1);
            sprMain.drawString("Scanning...", DISPLAY_WIDTH/2, DISPLAY_HEIGHT/2);
            return;
        }

        int itemH = 34;
        int startY = 52;
        for (uint8_t i = 0; i < netCount && i < 6; i++) {
            int y = startY + i * itemH;
            bool sel = (i == netSel);
            if (sel) {
                sprMain.fillRoundRect(4, y, DISPLAY_WIDTH-8, itemH-2, 3, T().highlight);
                if (activeTheme == THEME_INK)
                    sprMain.drawRoundRect(4, y, DISPLAY_WIDTH-8, itemH-2, 3, T().accent);
            }

            // Signal bars
            int bars = (nets[i].rssi > -50) ? 4 : (nets[i].rssi > -65) ? 3 : (nets[i].rssi > -75) ? 2 : 1;
            for (uint8_t b = 0; b < 4; b++) {
                uint16_t bc = (b < bars) ? T().ok : T().bg2;
                sprMain.fillRect(10 + b*6, y + 20 - b*3, 4, 4 + b*3, bc);
            }

            // SSID
            sprMain.setTextColor(sel ? T().text : T().textDim, T().bg);
            sprMain.setTextDatum(ML_DATUM);
            sprMain.setTextSize(sel ? 2 : 1);
            sprMain.drawString(nets[i].ssid, 40, y + itemH/2);

            if (activeTheme == THEME_INK && i < netCount-1)
                sprMain.drawFastHLine(8, y+itemH-1, DISPLAY_WIDTH-16, T().border);
        }

        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(BC_DATUM);
        sprMain.setTextSize(1);
        sprMain.drawString("OK=Connect (say password)  BACK=Menu", DISPLAY_WIDTH/2, DISPLAY_HEIGHT-4);
    }

    // ══════════════════════════════════════════════════════════
    //  SETTINGS SCREEN
    // ══════════════════════════════════════════════════════════
    uint8_t settingsSel = 0;

    void drawSettings() {
        sprMain.setTextColor(T().text, T().bg);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("Settings", 10, 28);
        sprMain.drawFastHLine(0, 48, DISPLAY_WIDTH, T().border);

        // Theme selector
        int y = 56;
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextSize(1);
        sprMain.drawString("THEME", 10, y);
        y += 14;

        for (uint8_t i = 0; i < THEME_COUNT; i++) {
            bool sel = (i == (uint8_t)activeTheme);
            bool cur = (settingsSel == i);
            int bx = 10 + i * 112;

            uint16_t bg   = sel ? T().accent : T().bg2;
            uint16_t fg   = sel ? T().textInvert : T().text;
            uint16_t bord = cur ? T().ok : T().border;

            sprMain.fillRoundRect(bx, y, 104, 36, 4, bg);
            sprMain.drawRoundRect(bx, y, 104, 36, 4, bord);
            if (cur) sprMain.drawRoundRect(bx+1, y+1, 102, 34, 3, bord); // double border
            sprMain.setTextColor(fg, bg);
            sprMain.setTextDatum(MC_DATUM);
            sprMain.setTextSize(1);
            sprMain.drawString(THEMES[i].name, bx + 52, y + 12);
            if (sel) {
                sprMain.setTextSize(1);
                sprMain.drawString("ACTIVE", bx + 52, y + 24);
            }
        }

        y += 48;
        sprMain.drawFastHLine(0, y, DISPLAY_WIDTH, T().border);
        y += 8;

        // Server info
        extern char serverHost[];
        char buf[60];
        snprintf(buf, 60, "Server: %s:%d", serverHost, SERVER_PORT);
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.setTextSize(1);
        sprMain.drawString(buf, 10, y); y += 18;

        // Version
        sprMain.drawString("VoiceDesk v1.0  (c) 2026", 10, y);

        _drawNavHint("LEFT/RIGHT=Theme  OK=Apply  BACK=Menu");
    }

    // ══════════════════════════════════════════════════════════
    //  ERROR SCREEN
    // ══════════════════════════════════════════════════════════
    void drawError() {
        int cx = DISPLAY_WIDTH / 2;
        int cy = 130;

        sprMain.fillCircle(cx, cy, 55, T().faceBg);
        sprMain.drawCircle(cx, cy, 55, T().err);
        faceState = FACE_ERROR;
        drawFaceOnSprite(sprMain, cx, cy);

        sprMain.setTextColor(T().err, T().bg);
        sprMain.setTextDatum(TC_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("Oops!", cx, 28);

        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextSize(1);
        sprMain.drawString(errorText, cx, 200);

        _drawNavHint("OK=Retry  BACK=Home");
    }

    // ══════════════════════════════════════════════════════════
    //  SYNCING SCREEN
    // ══════════════════════════════════════════════════════════
    void drawSyncing() {
        int cx = DISPLAY_WIDTH / 2;
        sprMain.setTextColor(T().accent, T().bg);
        sprMain.setTextDatum(MC_DATUM);
        sprMain.setTextSize(2);
        sprMain.drawString("Syncing...", cx, DISPLAY_HEIGHT/2 - 20);

        // Spinning arc
        for (int i = 0; i < 12; i++) {
            float angle = (i / 12.0f) * 2 * PI + animFrame * 0.2f;
            int x = cx + 35 * cos(angle);
            int y = DISPLAY_HEIGHT/2 + 20 + 35 * sin(angle);
            uint8_t bright = (i * 21) % 255;
            uint16_t col = sprMain.alphaBlend(bright, T().accent, T().bg);
            sprMain.fillCircle(x, y, 4, col);
        }

        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextSize(1);
        sprMain.drawString(subText, cx, DISPLAY_HEIGHT/2 + 70);
    }

private:
    // ── Drawing helpers ──────────────────────────────────────
    void _drawEye(TFT_eSprite& spr, int cx, int cy, int r, bool squint) {
        if (squint) {
            // Half eye
            spr.fillRect(cx - r, cy, r*2, r, T().faceEye);
        } else {
            spr.fillCircle(cx, cy, r, T().faceEye);
            spr.fillCircle(cx + 2, cy + 1, r/2, T().facePupil); // pupil
        }
    }

    void _drawSmile(TFT_eSprite& spr, int cx, int cy, int w, int depth, uint16_t col) {
        // Draw a simple arc smile using a series of points
        for (int x = -w; x <= w; x++) {
            float t = (float)x / w;
            int y = cy + (int)(depth * t * t); // parabola
            spr.drawPixel(cx + x, y, col);
            spr.drawPixel(cx + x, y + 1, col);
        }
    }

    void _drawField(const char* label, const char* value, int y) {
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextSize(1);
        sprMain.setTextDatum(TL_DATUM);
        sprMain.drawString(label, 10, y);
        sprMain.setTextColor(T().text, T().bg);
        sprMain.drawString(value, 100, y);
        if (activeTheme == THEME_INK)
            sprMain.drawFastHLine(8, y + 18, DISPLAY_WIDTH - 16, T().border);
    }

    void _drawNavHint(const char* hint) {
        sprMain.setTextColor(T().textDim, T().bg);
        sprMain.setTextDatum(BC_DATUM);
        sprMain.setTextSize(1);
        sprMain.drawString(hint, DISPLAY_WIDTH / 2, DISPLAY_HEIGHT - 4);
    }

    void _drawWrappedText(const char* text, int x, int y, int maxW, int maxH) {
        // Simple character-count wrap (6px per char at size 1)
        int charsPerLine = maxW / 6;
        int lineH = 12;
        int lines = maxH / lineH;
        int len = strlen(text);
        int pos = 0;
        for (int l = 0; l < lines && pos < len; l++) {
            char line[64] = {};
            strncpy(line, text + pos, min(charsPerLine, len - pos));
            sprMain.drawString(line, x, y + l * lineH);
            pos += charsPerLine;
        }
    }

    uint16_t _dimColor(uint16_t col) {
        uint8_t r = (col >> 11) & 0x1F;
        uint8_t g = (col >> 5)  & 0x3F;
        uint8_t b =  col        & 0x1F;
        return ((r/2) << 11) | ((g/2) << 5) | (b/2);
    }
};
