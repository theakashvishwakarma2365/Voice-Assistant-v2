#pragma once
#include <Arduino.h>
#include <SD.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "config.h"

// ════════════════════════════════════════════════════════════════
//  Storage — SD card queue + NVS preferences
// ════════════════════════════════════════════════════════════════

static Preferences prefs;

// ── NVS (WiFi creds, server host, theme) ─────────────────────
void nvs_init() { prefs.begin(NVS_NAMESPACE, false); }

String nvs_get(const char* key, const char* def = "") {
    return prefs.getString(key, def);
}
void nvs_set(const char* key, const char* val) {
    prefs.putString(key, val);
}
int nvs_get_int(const char* key, int def = 0) {
    return prefs.getInt(key, def);
}
void nvs_set_int(const char* key, int val) {
    prefs.putInt(key, val);
}

// ── SD card ──────────────────────────────────────────────────
bool sd_init() {
    if (!SD.begin(SD_CS)) {
        Serial.println("[SD] Init failed");
        return false;
    }
    SD.mkdir(SD_ROOT);
    SD.mkdir(SD_QUEUE_DIR);
    SD.mkdir(SD_SYNCED_DIR);
    Serial.println("[SD] Ready");
    return true;
}

// Count pending items in queue
uint8_t sd_queue_count() {
    uint8_t count = 0;
    File dir = SD.open(SD_QUEUE_DIR);
    while (true) {
        File f = dir.openNextFile();
        if (!f) break;
        if (!f.isDirectory()) count++;
        f.close();
    }
    dir.close();
    return count;
}

// Write JSON string to queue
bool sd_queue_write(const char* type, const char* json) {
    char path[80];
    snprintf(path, 80, "%s/%s_%lu.json", SD_QUEUE_DIR, type, millis());
    File f = SD.open(path, FILE_WRITE);
    if (!f) return false;
    f.println(json);
    f.close();
    return true;
}

// Queue a task for offline
void sd_queue_task(const char* title, const char* sheet,
                   const char* dueDate = "", const char* priority = "normal",
                   const char* remarks = "") {
    StaticJsonDocument<256> doc;
    doc["title"]    = title;
    doc["sheet"]    = sheet;
    doc["due_date"] = dueDate;
    doc["priority"] = priority;
    doc["remarks"]  = remarks;
    char buf[256];
    serializeJson(doc, buf, 256);
    sd_queue_write("task", buf);
}

// Read and flush entire queue — calls cb for each item
// cb(type, jsonPayload) — returns true if item was accepted by server
void sd_queue_flush(std::function<bool(const char*, const char*)> cb) {
    File dir = SD.open(SD_QUEUE_DIR);
    while (true) {
        File entry = dir.openNextFile();
        if (!entry) break;
        if (entry.isDirectory()) { entry.close(); continue; }

        // Read content
        String content = "";
        while (entry.available()) content += (char)entry.read();
        String name = String(entry.name());
        entry.close();

        // Determine type from filename prefix
        const char* type = "task";
        if (name.startsWith("meeting")) type = "meeting";

        if (cb(type, content.c_str())) {
            // Move to synced
            char src[80], dst[80];
            snprintf(src, 80, "%s/%s", SD_QUEUE_DIR, name.c_str());
            snprintf(dst, 80, "%s/%s", SD_SYNCED_DIR, name.c_str());
            SD.rename(src, dst);
        }
    }
    dir.close();
}
