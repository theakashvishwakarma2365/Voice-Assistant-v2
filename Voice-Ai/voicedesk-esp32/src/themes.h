#pragma once
#include <TFT_eSPI.h>

// ═══════════════════════════════════════════════════════════════
//  VoiceDesk Theme System
//  Add a new theme by adding an entry to the Theme array below.
//  Switch at runtime with: UI.setTheme(THEME_DARK);
// ═══════════════════════════════════════════════════════════════

// ── TFT 16-bit colour helpers ────────────────────────────────
#define RGB16(r,g,b) ((uint16_t)(((r & 0xF8)<<8)|((g & 0xFC)<<3)|((b & 0xF8)>>3)))

// ── Theme IDs ────────────────────────────────────────────────
enum ThemeID {
    THEME_INK    = 0,   // e-ink / paper white  (DEFAULT)
    THEME_DARK   = 1,   // deep navy / OLED dark
    THEME_RETRO  = 2,   // amber terminal
    THEME_NEON   = 3,   // cyberpunk neon
    THEME_COUNT  = 4
};

// ── Theme struct ─────────────────────────────────────────────
struct Theme {
    const char* name;

    // Background layers
    uint16_t bg;            // main background
    uint16_t bg2;           // card / panel background
    uint16_t border;        // borders, dividers

    // Text
    uint16_t text;          // primary text
    uint16_t textDim;       // secondary / hint text
    uint16_t textInvert;    // text on accent bg

    // Accents
    uint16_t accent;        // primary accent (headings, icons)
    uint16_t accentDim;     // muted accent
    uint16_t highlight;     // selected item bg

    // Status colours
    uint16_t ok;            // success / online
    uint16_t warn;          // warning / pending
    uint16_t err;           // error / offline

    // Face colours
    uint16_t faceEye;       // eye fill
    uint16_t facePupil;     // pupil
    uint16_t faceMouth;     // mouth stroke
    uint16_t faceBg;        // face circle bg

    // Status bar
    uint16_t statusBar;     // top bar background
    uint16_t statusText;    // top bar text

    // Font sizes (scale hints only)
    uint8_t fontLarge;      // title font size
    uint8_t fontMed;        // body font size
    uint8_t fontSmall;      // caption font size
};

// ════════════════════════════════════════════════════════════════
//  THEME DEFINITIONS
// ════════════════════════════════════════════════════════════════

static const Theme THEMES[THEME_COUNT] = {

    // ── 0: INK (e-ink paper style) ──────────────────────────
    {
        .name        = "Ink",
        .bg          = RGB16(245,245,240),  // warm off-white paper
        .bg2         = RGB16(255,255,255),  // pure white card
        .border      = RGB16(180,175,165),  // warm grey line
        .text        = RGB16(20, 20, 20),   // near-black ink
        .textDim     = RGB16(110,105,100),  // faded ink
        .textInvert  = RGB16(245,245,240),  // paper on dark
        .accent      = RGB16(30, 30, 30),   // strong ink
        .accentDim   = RGB16(90, 90, 85),
        .highlight   = RGB16(215,210,200),  // light smudge
        .ok          = RGB16(40, 120, 60),  // dark green stamp
        .warn        = RGB16(180,120,  0),  // sepia amber
        .err         = RGB16(160, 30, 30),  // dark red stamp
        .faceEye     = RGB16(20, 20, 20),
        .facePupil   = RGB16(245,245,240),
        .faceMouth   = RGB16(20, 20, 20),
        .faceBg      = RGB16(255,255,255),
        .statusBar   = RGB16(30, 30, 30),
        .statusText  = RGB16(245,245,240),
        .fontLarge   = 4,
        .fontMed     = 2,
        .fontSmall   = 1,
    },

    // ── 1: DARK (deep navy OLED) ────────────────────────────
    {
        .name        = "Dark",
        .bg          = RGB16( 10, 12, 20),  // near black navy
        .bg2         = RGB16( 20, 25, 40),  // card dark
        .border      = RGB16( 40, 50, 80),  // subtle blue border
        .text        = RGB16(220,225,235),  // soft white
        .textDim     = RGB16(100,110,135),  // muted blue-grey
        .textInvert  = RGB16( 10, 12, 20),
        .accent      = RGB16( 90,170,255),  // electric blue
        .accentDim   = RGB16( 40, 80,140),
        .highlight   = RGB16( 30, 40, 70),  // selection glow
        .ok          = RGB16( 60,220,120),  // bright green
        .warn        = RGB16(255,190,  0),  // amber
        .err         = RGB16(255, 70, 70),  // bright red
        .faceEye     = RGB16(220,225,235),
        .facePupil   = RGB16( 10, 12, 20),
        .faceMouth   = RGB16( 90,170,255),
        .faceBg      = RGB16( 20, 25, 40),
        .statusBar   = RGB16(  5,  8, 15),
        .statusText  = RGB16( 90,170,255),
        .fontLarge   = 4,
        .fontMed     = 2,
        .fontSmall   = 1,
    },

    // ── 2: RETRO (amber terminal) ───────────────────────────
    {
        .name        = "Retro",
        .bg          = RGB16( 12,  8,  0),  // dark screen
        .bg2         = RGB16( 20, 14,  0),
        .border      = RGB16( 80, 55,  0),
        .text        = RGB16(255,180, 20),  // amber phosphor
        .textDim     = RGB16(160,100,  0),
        .textInvert  = RGB16( 12,  8,  0),
        .accent      = RGB16(255,200, 50),  // bright amber
        .accentDim   = RGB16(150, 90,  0),
        .highlight   = RGB16( 50, 35,  0),
        .ok          = RGB16(180,255, 80),  // phosphor green
        .warn        = RGB16(255,160,  0),
        .err         = RGB16(255, 60, 20),  // orange-red CRT
        .faceEye     = RGB16(255,180, 20),
        .facePupil   = RGB16( 12,  8,  0),
        .faceMouth   = RGB16(255,200, 50),
        .faceBg      = RGB16( 20, 14,  0),
        .statusBar   = RGB16(  8,  5,  0),
        .statusText  = RGB16(255,200, 50),
        .fontLarge   = 4,
        .fontMed     = 2,
        .fontSmall   = 1,
    },

    // ── 3: NEON (cyberpunk) ─────────────────────────────────
    {
        .name        = "Neon",
        .bg          = RGB16(  5,  0, 15),  // deep purple-black
        .bg2         = RGB16( 15,  5, 30),
        .border      = RGB16( 80,  0,120),  // purple neon
        .text        = RGB16(240,230,255),  // lavender white
        .textDim     = RGB16(140,100,180),
        .textInvert  = RGB16(  5,  0, 15),
        .accent      = RGB16(255,  0,200),  // hot pink
        .accentDim   = RGB16(140,  0,110),
        .highlight   = RGB16( 40,  0, 60),
        .ok          = RGB16(  0,255,180),  // cyan-green
        .warn        = RGB16(255,200,  0),
        .err         = RGB16(255, 30, 80),  // neon red
        .faceEye     = RGB16(  0,255,200),  // cyan eyes
        .facePupil   = RGB16(  5,  0, 15),
        .faceMouth   = RGB16(255,  0,200),  // pink mouth
        .faceBg      = RGB16( 15,  5, 30),
        .statusBar   = RGB16(  3,  0, 10),
        .statusText  = RGB16(255,  0,200),
        .fontLarge   = 4,
        .fontMed     = 2,
        .fontSmall   = 1,
    },
};

// ── Active theme accessor ────────────────────────────────────
extern ThemeID activeTheme;
inline const Theme& T() { return THEMES[activeTheme]; }
