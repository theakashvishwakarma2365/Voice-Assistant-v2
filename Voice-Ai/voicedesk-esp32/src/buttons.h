#pragma once
#include <Arduino.h>
#include "config.h"

// ════════════════════════════════════════════════════════════════
//  Button handler — debounce, short press, long press
// ════════════════════════════════════════════════════════════════

enum ButtonID { BTN_ID_BACK=0, BTN_ID_UP, BTN_ID_DOWN, BTN_ID_OK, BTN_ID_MIC, BTN_COUNT };
enum ButtonEvent { NONE=0, SHORT_PRESS, LONG_PRESS, HELD };

struct ButtonState {
    uint8_t  pin;
    bool     lastRaw;
    bool     debounced;
    uint32_t pressedAt;
    bool     longFired;
};

static ButtonState BTN_STATES[BTN_COUNT] = {
    { BTN_BACK, true, true, 0, false },
    { BTN_UP,   true, true, 0, false },
    { BTN_DOWN, true, true, 0, false },
    { BTN_OK,   true, true, 0, false },
    { BTN_MIC,  true, true, 0, false },
};

void buttons_init() {
    uint8_t pins[] = { BTN_BACK, BTN_UP, BTN_DOWN, BTN_OK, BTN_MIC };
    for (auto p : pins) pinMode(p, INPUT_PULLUP);
}

// Call every loop() — returns event for each button
ButtonEvent buttons_poll(ButtonID id) {
    auto& b = BTN_STATES[id];
    bool raw = digitalRead(b.pin) == LOW;  // active LOW
    uint32_t now = millis();

    // Debounce
    if (raw != b.lastRaw) {
        b.lastRaw = raw;
        // just changed — wait for debounce
        b.pressedAt = now;
        return NONE;
    }

    if (raw != b.debounced && (now - b.pressedAt) >= BTN_DEBOUNCE_MS) {
        b.debounced = raw;
        if (raw) {
            b.pressedAt = now;
            b.longFired = false;
        } else {
            if (!b.longFired)
                return SHORT_PRESS;
        }
    }

    if (b.debounced && !b.longFired && (now - b.pressedAt) >= BTN_LONG_PRESS_MS) {
        b.longFired = true;
        return LONG_PRESS;
    }

    if (b.debounced && b.longFired)
        return HELD;

    return NONE;
}

bool buttons_is_held(ButtonID id) {
    return BTN_STATES[id].debounced;
}
