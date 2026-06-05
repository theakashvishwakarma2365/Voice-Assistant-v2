#pragma once
#include <Arduino.h>
#include <driver/i2s.h>
#include "config.h"

// ════════════════════════════════════════════════════════════════
//  Audio I/O — INMP441 mic (I2S0) + MAX98357A speaker (I2S1)
// ════════════════════════════════════════════════════════════════

// ── Mic (I2S0 RX) ────────────────────────────────────────────
void mic_init() {
    i2s_config_t cfg = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate          = MIC_SAMPLE_RATE,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = 4,
        .dma_buf_len          = MIC_BUFFER_SIZE,
        .use_apll             = false,
    };
    i2s_pin_config_t pins = {
        .bck_io_num   = MIC_SCK,
        .ws_io_num    = MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = MIC_SD,
    };
    i2s_driver_install(MIC_PORT, &cfg, 0, nullptr);
    i2s_set_pin(MIC_PORT, &pins);
    i2s_zero_dma_buffer(MIC_PORT);
}

// Read 16-bit PCM samples. Returns number of bytes read.
// INMP441 sends 32-bit, we keep upper 16 bits.
size_t mic_read(int16_t* buf, size_t samples) {
    int32_t raw[samples];
    size_t bytesRead = 0;
    i2s_read(MIC_PORT, raw, samples * sizeof(int32_t), &bytesRead, portMAX_DELAY);
    size_t got = bytesRead / sizeof(int32_t);
    for (size_t i = 0; i < got; i++)
        buf[i] = (int16_t)(raw[i] >> 16);
    return got * sizeof(int16_t);
}

// Compute RMS level 0-100 for display bar
uint8_t mic_level(const int16_t* buf, size_t samples) {
    int64_t sum = 0;
    for (size_t i = 0; i < samples; i++)
        sum += (int64_t)buf[i] * buf[i];
    float rms = sqrt((float)sum / samples);
    return (uint8_t)min(100.0f, rms / 327.0f);
}

// Silence detection
bool mic_is_silent(const int16_t* buf, size_t samples, int16_t threshold = 400) {
    for (size_t i = 0; i < samples; i++)
        if (abs(buf[i]) > threshold) return false;
    return true;
}

// ── Speaker (I2S1 TX) ─────────────────────────────────────────
void spk_init() {
    i2s_config_t cfg = {
        .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate          = 22050,
        .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count        = 8,
        .dma_buf_len          = 512,
        .use_apll             = false,
    };
    i2s_pin_config_t pins = {
        .bck_io_num   = SPK_BCLK,
        .ws_io_num    = SPK_LRC,
        .data_out_num = SPK_DIN,
        .data_in_num  = I2S_PIN_NO_CHANGE,
    };
    i2s_driver_install(SPK_PORT, &cfg, 0, nullptr);
    i2s_set_pin(SPK_PORT, &pins);
}

// Play raw 16-bit PCM buffer
void spk_play_pcm(const int16_t* buf, size_t samples) {
    size_t written = 0;
    i2s_write(SPK_PORT, buf, samples * sizeof(int16_t), &written, portMAX_DELAY);
}

// Play WAV from byte buffer (skips 44-byte WAV header)
void spk_play_wav(const uint8_t* wavData, size_t wavLen) {
    if (wavLen < 44) return;
    const int16_t* pcm = (const int16_t*)(wavData + 44);
    size_t samples = (wavLen - 44) / sizeof(int16_t);
    size_t written = 0;
    // Write in chunks
    size_t chunkSamples = 512;
    for (size_t i = 0; i < samples; i += chunkSamples) {
        size_t n = min(chunkSamples, samples - i);
        i2s_write(SPK_PORT, pcm + i, n * sizeof(int16_t), &written, portMAX_DELAY);
    }
}

void spk_stop() {
    i2s_zero_dma_buffer(SPK_PORT);
}
