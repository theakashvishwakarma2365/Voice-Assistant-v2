// ════════════════════════════════════════════════════════════════
//  TFT_eSPI User Setup for VoiceDesk
//  Copy this file to your TFT_eSPI library folder and replace
//  the existing User_Setup.h
//  Path: Arduino/libraries/TFT_eSPI/User_Setup.h
// ════════════════════════════════════════════════════════════════

// ── Driver ───────────────────────────────────────────────────
#define ILI9486_DRIVER      // MPI3501 uses ILI9486

// ── Display size ─────────────────────────────────────────────
#define TFT_WIDTH   320
#define TFT_HEIGHT  480

// ── Pins ─────────────────────────────────────────────────────
#define TFT_CS   15
#define TFT_DC    2
#define TFT_RST   4
#define TFT_MOSI 23
#define TFT_SCLK 18
#define TFT_MISO 19    // Not used (touch disabled) but defined for SPI bus

// ── SPI speed ────────────────────────────────────────────────
#define SPI_FREQUENCY       27000000   // 27MHz — safe for ILI9486
#define SPI_READ_FREQUENCY   5000000

// ── Colour order ─────────────────────────────────────────────
// ILI9486 typically needs BGR
#define TFT_BGR_ORDER 1

// ── Fonts to include ─────────────────────────────────────────
#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT6
#define LOAD_FONT7
#define LOAD_FONT8
#define LOAD_GFXFF
#define SMOOTH_FONT
