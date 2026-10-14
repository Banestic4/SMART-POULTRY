/*
 * SMART-Poultry - ESP32 firmware
 * Reads DHT22 (temperature, humidity) and MQ135 (air quality) and sends them to the
 * Flask backend over Wi-Fi as JSON.
 *
 * Wiring (see README):
 *   DHT22  : pin1 VCC -> 3V3 | pin2 DATA -> GPIO4 (+10k resistor DATA<->3V3) | pin4 GND -> GND
 *   MQ135  : VCC -> VIN (5V) | GND -> GND | AO -> 10k -> junction -> 15k -> GND ; junction -> GPIO34
 *
 * Arduino IDE setup:
 *   Board   : "ESP32 Dev Module"  (esp32 by Espressif Systems in Boards Manager)
 *   Library : "DHT sensor library" by Adafruit (accept "Install all" for Adafruit Unified Sensor)
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>

// ======================= USER SETTINGS (edit these) =======================
const char* WIFI_SSID  = "YOUR_HOTSPOT_NAME";
const char* WIFI_PASS  = "YOUR_HOTSPOT_PASSWORD";
// IP address of the laptop running the backend (see README: run "ipconfig" on the laptop)
const char* SERVER_URL = "http://192.168.43.100:5000/api/readings";
const char* API_KEY    = "sp-device-key-123";     // must equal SP_DEVICE_API_KEY on the server
const char* DEVICE_ID  = "esp32-01";
const unsigned long SEND_INTERVAL_MS = 5000;      // DHT22 needs >= 2 s between reads
// ==========================================================================

#define DHT_PIN   4
#define DHT_TYPE  DHT22
#define MQ_PIN    34        // ADC1 channel: keeps working while Wi-Fi is on
#define LED_PIN   2         // on-board LED on most ESP32 dev boards

DHT dht(DHT_PIN, DHT_TYPE);
unsigned long lastSend = 0;
int dhtFailures = 0;

int readMQ135() {
  long sum = 0;
  for (int i = 0; i < 16; i++) {      // average 16 samples to reduce ADC noise
    sum += analogRead(MQ_PIN);
    delay(5);
  }
  return (int)(sum / 16);             // 0..4095 (12-bit)
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("Connecting to Wi-Fi '%s' ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\nConnected. ESP32 IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\nWi-Fi connection failed, will retry.");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(MQ_PIN, ADC_11db);   // full 0-3.3 V range
  dht.begin();
  Serial.println("\nSMART-Poultry node starting. MQ135 needs a few minutes to warm up.");
  connectWiFi();
}

void loop() {
  if (millis() - lastSend < SEND_INTERVAL_MS) return;
  lastSend = millis();

  float t = dht.readTemperature();
  float h = dht.readHumidity();
  int gas = readMQ135();

  if (isnan(t) || isnan(h)) {
    dhtFailures++;
    Serial.printf("DHT22 read failed (%d). Check wiring and the 10k pull-up.\n", dhtFailures);
    return;                            // never send invalid data
  }
  Serial.printf("T=%.1f C  RH=%.1f %%  MQ135 raw=%d\n", t, h, gas);

  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return;

  char body[160];
  snprintf(body, sizeof(body),
           "{\"device_id\":\"%s\",\"temperature\":%.1f,\"humidity\":%.1f,\"gas_raw\":%d}",
           DEVICE_ID, t, h, gas);

  HTTPClient http;
  http.setTimeout(5000);
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  int code = http.POST((uint8_t*)body, strlen(body));
  if (code == 201) {
    Serial.println("  -> sent OK");
    digitalWrite(LED_PIN, HIGH); delay(80); digitalWrite(LED_PIN, LOW);
  } else {
    Serial.printf("  -> server error/unreachable (code %d)\n", code);
  }
  http.end();
}
