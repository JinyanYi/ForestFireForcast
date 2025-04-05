#include <SPI.h>
#include <WiFiClient.h>
#include <HttpClient.h>
#include <ESP8266WiFi.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

#define LED D13

// Wifi配置
const char* ssid = "";
const char* pass = "";

// 服务器配置
const char* server = "172.20.10.7";
const uint16_t port = 50000;

// LCD配置
LiquidCrystal_I2C lcd(0x27, 16, 2);

// JSON解析文档
DynamicJsonDocument doc(1024);

// 数据存储
int warningCount = 0;
unsigned long lastUpdateTime = 0;
const unsigned long updateInterval = 5000;

WiFiClient espClient;
HttpClient http(espClient, server, port);

void setup() {
  Serial.begin(9600);
  pinMode(LED, OUTPUT);
  digitalWrite(LED, HIGH);
  
  // 初始化LCD
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi");
  
  // 连接WiFi
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.print("Connected to ");
  Serial.println(WiFi.localIP());
  
  // 显示连接成功
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("WiFi Connected");
  lcd.setCursor(0, 1);
  lcd.print(WiFi.localIP());
  delay(2000);
  
  // 设置初始显示
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Station 1");
  lcd.setCursor(0, 1);
  lcd.print("Warnings: 0");
}

void loop() {
  unsigned long currentMillis = millis();
  
  if (currentMillis - lastUpdateTime >= updateInterval) {
    lastUpdateTime = currentMillis;
    fetchLatestData();
    updateLCD();
  }
}

void fetchLatestData() {
  int err = http.get("/api/debug");
  if (err == 0) {
    Serial.println("API call successful");
    
    err = http.responseStatusCode();
    if (err == 200) {
      String response = http.responseBody();
      Serial.println("Response received");
      
      DeserializationError error = deserializeJson(doc, response);
      if (!error) {
        // 获取警告计数
        warningCount = doc["warnings"];
        
        Serial.print("Warning Count: ");
        Serial.println(warningCount);

        // LED指示：如果有警告则点亮
        if (warningCount > 0) {
          digitalWrite(LED, LOW);  // 有警告时LED亮
        } else {
          digitalWrite(LED, HIGH); // 无警告时LED灭
        }
        
      } else {
        Serial.print("JSON parsing failed: ");
        Serial.println(error.c_str());
      }
    } else {
      Serial.print("Server error: ");
      Serial.println(err);
    }
  } else {
    Serial.print("API call failed: ");
    Serial.println(err);
    delay(1000);
  }
}

void updateLCD() {
  // 第一行保持显示 "Station 1"
  
  // 更新第二行的警告计数
  lcd.setCursor(0, 1);
  lcd.print("Warnings: ");
  lcd.print(warningCount);
  lcd.print("   ");  // 清除残留字符
}