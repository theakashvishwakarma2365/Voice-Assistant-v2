#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "storage.h"

using namespace websockets;

// ════════════════════════════════════════════════════════════════
//  Network — WiFi + WebSocket client
// ════════════════════════════════════════════════════════════════

static WebsocketsClient wsClient;
static bool wsConnected = false;
static char serverHost[64] = SERVER_DEFAULT_HOST;

// Callbacks (set by main)
static std::function<void(const char*)> onMessage;
static std::function<void()>            onConnect;
static std::function<void()>            onDisconnect;

// ── WiFi ──────────────────────────────────────────────────────
bool wifi_connect(const char* ssid, const char* pass, uint32_t timeoutMs = WIFI_CONNECT_TIMEOUT) {
    Serial.printf("[WiFi] Connecting to %s\n", ssid);
    WiFi.begin(ssid, pass);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeoutMs) {
        delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WiFi] Connected, IP: %s\n", WiFi.localIP().toString().c_str());
        return true;
    }
    Serial.println("[WiFi] Failed");
    return false;
}

bool wifi_is_connected() { return WiFi.status() == WL_CONNECTED; }

int wifi_scan(VoiceUI::WifiNet* nets, uint8_t maxNets) {
    int n = WiFi.scanNetworks();
    int count = min(n, (int)maxNets);
    for (int i = 0; i < count; i++) {
        strncpy(nets[i].ssid, WiFi.SSID(i).c_str(), 31);
        nets[i].rssi = WiFi.RSSI(i);
    }
    WiFi.scanDelete();
    return count;
}

// ── WebSocket ─────────────────────────────────────────────────
void ws_set_callbacks(
    std::function<void(const char*)> msgCb,
    std::function<void()> connectCb,
    std::function<void()> disconnectCb)
{
    onMessage    = msgCb;
    onConnect    = connectCb;
    onDisconnect = disconnectCb;
}

bool ws_connect() {
    char url[128];
    snprintf(url, 128, "ws://%s:%d%s", serverHost, SERVER_PORT, WS_PATH);
    Serial.printf("[WS] Connecting to %s\n", url);

    wsClient.onMessage([](WebsocketsMessage msg) {
        if (msg.isText() && onMessage)
            onMessage(msg.data().c_str());
    });
    wsClient.onEvent([](WebsocketsEvent event, String data) {
        if (event == WebsocketsEvent::ConnectionOpened) {
            wsConnected = true;
            Serial.println("[WS] Connected");
            if (onConnect) onConnect();
        } else if (event == WebsocketsEvent::ConnectionClosed) {
            wsConnected = false;
            Serial.println("[WS] Disconnected");
            if (onDisconnect) onDisconnect();
        }
    });

    return wsClient.connect(url);
}

void ws_loop() { if (wsConnected) wsClient.poll(); }

bool ws_send_audio(const uint8_t* data, size_t len) {
    if (!wsConnected) return false;
    return wsClient.sendBinary((const char*)data, len);
}

bool ws_send_json(const char* json) {
    if (!wsConnected) return false;
    return wsClient.send(json);
}

bool ws_send_audio_end() {
    return ws_send_json("{\"type\":\"audio_end\"}");
}

bool ws_is_connected() { return wsConnected; }

// ── HTTP helpers ──────────────────────────────────────────────
// Download WAV file from server audio cache
bool http_get_wav(const char* filename, uint8_t* buf, size_t bufLen, size_t& outLen) {
    char url[128];
    snprintf(url, 128, "http://%s:%d/api/audio/%s", serverHost, SERVER_PORT, filename);

    HTTPClient http;
    http.begin(url);
    int code = http.GET();
    if (code == 200) {
        outLen = http.getSize();
        if (outLen > bufLen) { http.end(); return false; }
        WiFiClient* stream = http.getStreamPtr();
        size_t got = 0;
        while (got < outLen) {
            size_t n = stream->read(buf + got, outLen - got);
            got += n;
        }
        http.end();
        return true;
    }
    http.end();
    return false;
}

// POST offline batch to server
bool http_post_offline(const char* type, const char* payload) {
    char url[128];
    snprintf(url, 128, "http://%s:%d/api/offline_batch", serverHost, SERVER_PORT);

    char body[512];
    snprintf(body, 512, "{\"items\":[{\"type\":\"%s\",\"data\":%s,\"queued_at\":\"now\"}]}", type, payload);

    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    http.end();
    return code == 200;
}

// GET task list from server
bool http_get_tasks(VoiceUI* ui, const char* sheetFilter = nullptr) {
    char url[128];
    snprintf(url, 128, "http://%s:%d/api/tasks", serverHost, SERVER_PORT);

    HTTPClient http;
    http.begin(url);
    int code = http.GET();
    if (code != 200) { http.end(); return false; }

    String resp = http.getString();
    http.end();

    StaticJsonDocument<4096> doc;
    DeserializationError err = deserializeJson(doc, resp);
    if (err) return false;

    ui->taskCount = 0;
    for (JsonObject task : doc.as<JsonArray>()) {
        if (ui->taskCount >= VoiceUI::MAX_TASKS) break;
        auto& t = ui->tasks[ui->taskCount++];
        strncpy(t.title,  task["title"]  | "?", 79);
        strncpy(t.status, task["status"] | "?", 15);
        strncpy(t.due,    task["due_date"] | "", 19);
        strncpy(t.sheet,  "", 31);  // sheet name needs separate lookup
    }
    return true;
}

// POST force sync
void http_force_sync() {
    char url[128];
    snprintf(url, 128, "http://%s:%d/api/sync", serverHost, SERVER_PORT);
    HTTPClient http;
    http.begin(url);
    http.POST("");
    http.end();
}
