# Raspberry Pi Zero Compatibility Report
## XPT2046 Display · INMP441 Mic · MAX98357A Speaker

---

## Quick Verdict

✅ **Yes — Raspberry Pi Zero works with all three components**, and in many ways it's *easier* than ESP32 because Linux handles the I2S drivers, SPI drivers, and audio stack for you. The Pi Zero (and Pi Zero 2W) runs Raspberry Pi OS, so you get a real audio system (ALSA/PulseAudio), Python libraries, and pre-built overlays.

---

## Which Pi Zero?

| Board | CPU | RAM | WiFi | Verdict |
|-------|-----|-----|------|---------|
| Pi Zero v1.3 | 1GHz single-core ARM | 512MB | ❌ None | Works, add WiFi dongle |
| Pi Zero W | 1GHz single-core ARM | 512MB | ✅ 2.4GHz | ✅ Recommended |
| Pi Zero 2W | 1GHz quad-core ARM | 512MB | ✅ 2.4GHz | ✅ Best option |

The **Pi Zero 2W** is the best choice — same form factor, 4× the processing power, crucial for running voice recognition or audio processing.

---

## Component Compatibility

| Component | Pi Zero | Interface | Notes |
|-----------|---------|-----------|-------|
| XPT2046 touchscreen | ✅ Full support | SPI | Use `ads7846` kernel overlay |
| INMP441 microphone | ✅ Full support | I2S | Use `googlevoicehat-soundcard` or custom overlay |
| MAX98357A speaker | ✅ Full support | I2S | Use `hifiberry-dac` or `google-voicehat` overlay |
| All three together | ✅ Works | Mixed | Careful: only one I2S bus, mic+speaker share it |

> **Key difference from ESP32:** The Pi only has **one I2S bus**, but Linux's audio stack (ALSA) can handle full-duplex on a single bus — mic input and speaker output simultaneously — using the right overlay.

---

## GPIO Pin Map (BCM numbering)

All Pi Zero GPIO uses **3.3V logic**. The 40-pin header is identical to full-size Pi.

### XPT2046 Touchscreen + ILI9341 Display (SPI0)

```
Display Pin     →  Pi Zero GPIO (BCM)   Physical Pin
──────────────────────────────────────────────────────
VCC             →  3.3V                  Pin 1
GND             →  GND                   Pin 6
CS (display)    →  GPIO 8  (SPI0_CE0)    Pin 24
RESET           →  GPIO 25               Pin 22
DC / RS         →  GPIO 24               Pin 18
MOSI / SDI      →  GPIO 10 (SPI0_MOSI)   Pin 19
SCK / CLK       →  GPIO 11 (SPI0_CLK)    Pin 23
LED / BL        →  3.3V or GPIO 18       Pin 12
MISO / SDO      →  GPIO 9  (SPI0_MISO)   Pin 21

T_CS (touch)    →  GPIO 7  (SPI0_CE1)    Pin 26
T_CLK           →  GPIO 11 (shared SCK)  Pin 23
T_DIN           →  GPIO 10 (shared MOSI) Pin 19
T_DO            →  GPIO 9  (shared MISO) Pin 21
T_IRQ           →  GPIO 17               Pin 11
```

### INMP441 Microphone (I2S)

```
INMP441 Pin  →  Pi Zero GPIO (BCM)   Physical Pin
──────────────────────────────────────────────────
VDD          →  3.3V                  Pin 1
GND          →  GND                   Pin 6
SD (data)    →  GPIO 20 (I2S_SDI)     Pin 38
WS (LRCK)    →  GPIO 19 (I2S_LRCK)   Pin 35
SCK (BCLK)   →  GPIO 18 (I2S_BCLK)   Pin 12
L/R          →  GND (left) or 3.3V (right)
```

### MAX98357A Speaker Amplifier (I2S)

```
MAX98357A Pin  →  Pi Zero GPIO (BCM)   Physical Pin
────────────────────────────────────────────────────
VIN            →  5V                   Pin 2
GND            →  GND                  Pin 6
BCLK           →  GPIO 18 (I2S_BCLK)  Pin 12  ← shared with INMP441
LRCLK          →  GPIO 19 (I2S_LRCK)  Pin 35  ← shared with INMP441
DIN            →  GPIO 21 (I2S_SDO)   Pin 40
SD (shutdown)  →  leave floating (stays on)
```

> The INMP441 (input) and MAX98357A (output) share the same I2S clock lines (BCLK + LRCK) — this is correct and expected. They use separate data pins: GPIO 20 for mic input, GPIO 21 for speaker output.

---

## Complete GPIO Map (All Three Together)

```
Pi Zero BCM  │  Physical  │  Function
─────────────┼────────────┼────────────────────────────
GPIO 7       │  Pin 26    │  Touch CS (SPI0_CE1)
GPIO 8       │  Pin 24    │  Display CS (SPI0_CE0)
GPIO 9       │  Pin 21    │  SPI0 MISO
GPIO 10      │  Pin 19    │  SPI0 MOSI
GPIO 11      │  Pin 23    │  SPI0 CLK
GPIO 17      │  Pin 11    │  Touch IRQ (T_IRQ)
GPIO 18      │  Pin 12    │  I2S BCLK (mic + speaker)
GPIO 19      │  Pin 35    │  I2S LRCK (mic + speaker)
GPIO 20      │  Pin 38    │  I2S SDI  (mic data IN)
GPIO 21      │  Pin 40    │  I2S SDO  (speaker data OUT)
GPIO 24      │  Pin 18    │  Display DC
GPIO 25      │  Pin 22    │  Display RESET
```

No conflicts. All three peripherals coexist cleanly.

---

## Software Setup

### Step 1 — Enable SPI and I2S in /boot/config.txt

```ini
# Enable SPI for the display
dtparam=spi=on

# Enable I2S audio
dtparam=i2s=on

# MAX98357A speaker overlay
dtoverlay=hifiberry-dac

# OR use Google Voice HAT overlay (supports full-duplex mic+speaker)
# dtoverlay=googlevoicehat-soundcard
```

### Step 2 — Install display driver (fbdev or DRM)

For ILI9341 + XPT2046 on Pi Zero, the easiest path:

```bash
# Option A: Use notro/fbtft (framebuffer driver)
sudo apt install raspberrypi-kernel-headers
# Add to /boot/config.txt:
# dtoverlay=pitft28-resistive,rotate=90,speed=32000000,fps=20

# Option B: Use PyGame / luma.lcd in Python
pip install luma.lcd RPi.GPIO spidev
```

### Step 3 — Test audio

```bash
# Record from INMP441 (5 seconds)
arecord -D plughw:1,0 -f S32_LE -r 16000 -c 1 -d 5 test.wav

# Play back through MAX98357A
aplay -D plughw:1,0 test.wav
```

### Step 4 — Python example (mic + speaker)

```python
import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1

def audio_callback(indata, outdata, frames, time, status):
    # Echo mic to speaker (loopback test)
    outdata[:] = indata

with sd.Stream(samplerate=SAMPLE_RATE, channels=CHANNELS,
               callback=audio_callback):
    print("Streaming audio... Ctrl+C to stop")
    sd.sleep(10000)
```

---

## Pi Zero vs ESP32 — Which Should You Use?

| Feature | ESP32 | Pi Zero 2W |
|---------|-------|------------|
| Boot time | ~1 second | ~30-45 seconds |
| Power draw | ~80-240mA | ~300-500mA |
| Programming | Arduino C++ | Python, C, Node.js... |
| Audio stack | Manual I2S config | ALSA (automatic) |
| Voice AI libraries | Limited | Full Python ecosystem |
| Screen GUI | Low-level only | LVGL, PyGame, Qt |
| WiFi | Built-in | Built-in (W/2W) |
| Price | ~$5-8 | ~$15 |
| Runs LLM inference | ❌ No | ⚠️ Very slow |
| OTA updates | Custom | apt update |

**Choose Pi Zero if:** You want to run Python voice assistant code (like Whisper, pyttsx3, pvporcupine), use a GUI framework, or connect to cloud APIs easily.

**Choose ESP32 if:** You need instant-on, low power, battery operation, or a simple embedded project without Linux overhead.

---

## Known Gotchas for Pi Zero

1. **Only one I2S bus** — Unlike ESP32's two independent I2S ports, Pi has one. This is fine because Linux full-duplex works, but you cannot run two completely separate audio streams at different sample rates simultaneously.

2. **Pi Zero is 3.3V GPIO** — Same as ESP32. The INMP441 is happy. The MAX98357A VIN should still go to 5V (Pin 2 or 4) for best output volume — only the I2S logic signals are 3.3V.

3. **SPI display can be slow** — Pi Zero's SPI maxes at ~32MHz for the display. Still fast enough for a responsive UI.

4. **SD card reliability** — Pi Zero runs from a microSD card. Use a quality card (SanDisk/Samsung) and avoid power-cutting without proper shutdown — can corrupt the filesystem.

5. **No 3.5mm audio jack** — Pi Zero has no analog audio output (unlike full Pi). You must use the MAX98357A I2S route for audio output. The HDMI port carries audio but that's not useful here.

6. **Heat on Pi Zero 2W** — Under heavy audio + display load, the Zero 2W can throttle. A small heatsink is recommended.

---

## Summary

✅ **Pi Zero works with all three: XPT2046, INMP441, MAX98357A.**
The single I2S bus handles both mic and speaker in full-duplex via Linux ALSA.
SPI handles the display and touch controller with no conflicts.
The Pi Zero 2W is the best choice for any project involving voice processing or Python code.
