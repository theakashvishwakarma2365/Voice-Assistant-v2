# NodeMCU Compatibility Report
## XPT2046 Display · INMP441 Mic · MAX98357A Speaker

---

## ⚠️ Critical First Step: Which NodeMCU Do You Have?

"NodeMCU" refers to **two very different boards**:

| Board | Chip | I2S Input | I2S Output | Verdict |
|-------|------|-----------|------------|---------|
| NodeMCU v1/v2/v3 | **ESP8266** | ❌ Not supported | ✅ Limited | **DO NOT USE** for this project |
| NodeMCU-32S / ESP32 DevKit | **ESP32** | ✅ Full support | ✅ Full support | ✅ **USE THIS** |

The INMP441 microphone requires I2S **input** — the ESP8266 only supports I2S **output**. If you have an ESP8266-based NodeMCU, the microphone will not work. You need an **ESP32-based board**.

---

## Component Compatibility Summary

| Component | ESP8266 | ESP32 | Notes |
|-----------|---------|-------|-------|
| XPT2046 touchscreen | ✅ Works | ✅ Works | SPI interface, no issues |
| INMP441 microphone | ❌ No I2S input | ✅ Works great | I2S input peripheral required |
| MAX98357A speaker | ⚠️ Limited | ✅ Works great | I2S output; ESP8266 possible but buggy |
| All three together | ❌ Avoid | ✅ Possible | Requires careful pin planning |

---

## ESP32 Wiring — Complete Pin Map

### XPT2046 Touchscreen + ILI9341 Display (SPI Bus)

The XPT2046 is a **touch controller** typically soldered onto a 2.4" or 2.8" ILI9341 TFT display board. Both share the same SPI bus but use separate CS (chip select) pins.

```
Display Board Pin   →   ESP32 GPIO
─────────────────────────────────────
VCC                 →   3.3V
GND                 →   GND
CS  (display)       →   GPIO 15
RESET               →   GPIO 4
DC / RS             →   GPIO 2
MOSI / SDI          →   GPIO 23  (SPI MOSI)
SCK / CLK           →   GPIO 18  (SPI CLK)
LED / BL            →   3.3V (or GPIO for PWM brightness)
MISO / SDO          →   GPIO 19  (SPI MISO)

T_CLK  (touch)      →   GPIO 18  (shared with SCK)
T_CS   (touch)      →   GPIO 21  (separate CS!)
T_DIN  (touch)      →   GPIO 23  (shared with MOSI)
T_DO   (touch)      →   GPIO 19  (shared with MISO)
T_IRQ  (touch)      →   GPIO 36  (input-only pin, OK)
```

**Library:** Use **TFT_eSPI** — it supports XPT2046 touch natively. Configure `User_Setup.h` with the GPIO numbers above.

---

### INMP441 Microphone (I2S Input)

```
INMP441 Pin   →   ESP32 GPIO
──────────────────────────────
VDD           →   3.3V  ⚠️ 3.3V ONLY (not 5V!)
GND           →   GND
SD  (data)    →   GPIO 32
WS  (LRCK)    →   GPIO 25
SCK (BCLK)    →   GPIO 26
L/R           →   GND   (left channel stereo)
               OR  3.3V  (right channel stereo)
```

**I2S Config (Arduino):**
```cpp
i2s_config_t i2s_config = {
  .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
  .sample_rate = 16000,
  .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
  .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
  .communication_format = I2S_COMM_FORMAT_I2S,
  .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
  .dma_buf_count = 8,
  .dma_buf_len = 64,
};
```

---

### MAX98357A Speaker Amplifier (I2S Output)

```
MAX98357A Pin   →   ESP32 GPIO
────────────────────────────────
VIN             →   5V  (preferred) or 3.3V
GND             →   GND
BCLK            →   GPIO 27
LRC / LRCLK     →   GPIO 25  ← can share with INMP441 WS!
DIN             →   GPIO 22
SD (shutdown)   →   leave FLOATING (enables output)
GAIN            →   float = 9dB, GND = 12dB, VIN = 15dB
```

> **Speaker:** Connect an 8Ω or 4Ω speaker directly to the + / − output pins. The MAX98357A is a Class D amplifier — no extra components needed.

---

## Running INMP441 + MAX98357A Together (I2S Sharing)

Both devices use I2S. The ESP32 has **two I2S peripherals (I2S0 and I2S1)** — assign each device to a different one:

| Device | I2S Port | BCLK | LRCK/WS | DATA |
|--------|----------|------|---------|------|
| INMP441 (mic) | I2S_NUM_0 | GPIO 26 | GPIO 25 | GPIO 32 (RX) |
| MAX98357A (speaker) | I2S_NUM_1 | GPIO 27 | GPIO 25 | GPIO 22 (TX) |

> Note: LRCK/WS can be the same pin if both run at the same sample rate — or use separate pins for maximum flexibility.

---

## Complete GPIO Map (All Three Together)

```
ESP32 GPIO   │  Function
─────────────┼──────────────────────────────
GPIO 2       │  Display DC/RS
GPIO 4       │  Display RESET
GPIO 15      │  Display CS
GPIO 18      │  SPI CLK (display + touch)
GPIO 19      │  SPI MISO (display + touch)
GPIO 21      │  Touch CS (T_CS)
GPIO 22      │  MAX98357A DIN (I2S1 TX data)
GPIO 23      │  SPI MOSI (display + touch)
GPIO 25      │  I2S LRCK (shared mic + speaker)
GPIO 26      │  INMP441 BCLK (I2S0)
GPIO 27      │  MAX98357A BCLK (I2S1)
GPIO 32      │  INMP441 SD / data (I2S0 RX)
GPIO 36      │  T_IRQ (touch interrupt, input-only)
```

No pin conflicts. All three peripherals coexist.

---

## Known Limitations & Gotchas

1. **ESP8266 won't work for mic input** — This is the biggest gotcha. If you bought a cheap NodeMCU from a store without checking, it's probably ESP8266. Look for "ESP-12" module = ESP8266. Look for "ESP-WROOM-32" = ESP32.

2. **3.3V only for INMP441** — The INMP441 is not 5V tolerant. Connecting to 5V will likely destroy it.

3. **MAX98357A at 3.3V is quieter** — Runs at 3.3V but louder and more efficient at 5V. For a voice assistant, use 5V.

4. **GPIO 34, 35, 36, 39 are input-only on ESP32** — Don't try to use them for outputs (display CS, etc.). GPIO 36 for T_IRQ is fine since IRQ is input.

5. **SPI speed for display** — XPT2046 touch operates at max ~2.5 MHz SPI. The ILI9341 display runs up to ~40 MHz. TFT_eSPI handles switching speeds automatically.

6. **RAM constraints** — ESP32 has 520KB SRAM. Running audio buffers (mic + speaker) + display frame buffer simultaneously is tight. Use PSRAM-equipped ESP32 boards (ESP32-WROVER) if you plan DMA audio streaming.

7. **GPIO 12 boot issue** — Avoid GPIO 12 for critical connections; it affects boot voltage selection on some boards.

8. **I2S sample rate match** — Both I2S devices should run at compatible sample rates. 16000 Hz is typical for voice; 44100 Hz for music.

---

## Recommended Libraries

| Purpose | Library | Notes |
|---------|---------|-------|
| Display + Touch | **TFT_eSPI** | Best for ESP32 XPT2046 combos |
| I2S Mic input | **ESP32 Arduino I2S** (built-in) | `#include <driver/i2s.h>` |
| Audio playback | **ESP8266Audio** (works on ESP32) | MP3, WAV support |
| Audio (advanced) | **Arduino Audio Tools** (pschatzmann) | Full duplex, codec support |

---

## Summary Verdict

✅ **Yes, this combination works — but only on ESP32, not ESP8266.**

Use an **ESP32 DevKit** or **NodeMCU-32S** board. Wire XPT2046 on SPI, INMP441 on I2S0, and MAX98357A on I2S1. No pin conflicts exist in the map above. This is a well-proven combination used in many voice assistant and IoT display projects.
