#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <math.h>
#include "DHT.h"
#include <HardwareSerial.h>
#include "BluetoothSerial.h"
#include <SPI.h>
#include <LoRa.h>
// HSPI pin mapping
#define LORA_SCK 14
#define LORA_MISO 12
#define LORA_MOSI 13
#define LORA_SS 5
#define LORA_RST 15
#define LORA_DIO0 26
SPIClass SPI_LORA(HSPI);

unsigned long lastSendTime = 0;
const unsigned long sendInterval = 5000; // send every 5 seconds


#define DHTPIN 4      // 连接 DHT11 数据引脚的 ESP32 GPIO
#define DHTTYPE DHT11  // 传感器类型 DHT11
DHT dht(DHTPIN, DHTTYPE);
String receivedData = "";  // 存储完整的字符串
bool recording = false;    // 记录是否开始接收数据

Adafruit_ADS1115 ads;
const int windSensorPin = 34; // 选择一个 ADC 输入引脚
const float voltageRef = 3.3; // ESP32 的参考电压
const int adcResolution = 4095; // ESP32 ADC 12 位分辨率
// MQ-135 parameters remain unchanged
const float RL = 1.0;  // MQ module usually has RL=1kΩ
const float a_135 = 110.47;
const float b_135 = -2.862;
const float Ro_clean_air_ratio_135 = 3.6;
float R0_135;

// MQ-2 parameters (smoke)
const float a_2 = 574.25;
const float b_2 = -2.222;
const float Ro_clean_air_ratio_2 = 9.83;
float R0_2;

// MQ-7 parameters (carbon monoxide)
const float a_7 = 99.042;
const float b_7 = -1.518;
const float Ro_clean_air_ratio_7 = 27.5;
float R0_7;

// MQ-9 parameters (flammable gas)
const float a_9 = 1000.5;
const float b_9 = -2.186;
const float Ro_clean_air_ratio_9 = 9.6;
float R0_9;
BluetoothSerial SerialBT;

bool firstDataIgnored = false;

void setup() {
    Serial.begin(115200);
    SerialBT.begin("ESP32_Master", true); // 作为主机
    Serial.println("正在搜索 ESP32-CAM...");

  // 连接 ESP32-CAM
    if (!SerialBT.connected()) {
        Serial.println("⚠️ ESP32-CAM 断开连接，尝试重新连接...");
        connectToESP32CAM();
    }

    Wire.begin();
 // RX = GPI014
    dht.begin();
    if (!ads.begin(0x48)) {
        Serial.println("ADS1115 not detected!");
        while (1);
    }

    ads.setGain(GAIN_ONE);
    Serial.println("Sensor preheating (recommended 30 minutes)...");
    delay(5000);  // 30 minutes preheating

    // MQ-135 calibration
    float V_ADC_135 = ads.readADC_SingleEnded(0) * (4.096 / 32767.0);
    float RS_135 = RL * ((5.0 / V_ADC_135) - 1);
    R0_135 = RS_135 / Ro_clean_air_ratio_135;

    // MQ-2 calibration
    float V_ADC_2 = ads.readADC_SingleEnded(1) * (4.096 / 32767.0);
    float RS_2 = RL * ((5.0 / V_ADC_2) - 1);
    R0_2 = RS_2 / Ro_clean_air_ratio_2;

    // MQ-7 calibration
    float V_ADC_7 = ads.readADC_SingleEnded(2) * (4.096 / 32767.0);
    float RS_7 = RL * ((5.0 / V_ADC_7) - 1);
    R0_7 = RS_7 / Ro_clean_air_ratio_7;

    // MQ-9 calibration
    float V_ADC_9 = ads.readADC_SingleEnded(3) * (4.096 / 32767.0);
    float RS_9 = RL * ((5.0 / V_ADC_9) - 1);
    R0_9 = RS_9 / Ro_clean_air_ratio_9;

    Serial.println("All sensors calibrated!");
      SPI_LORA.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
    LoRa.setSPI(SPI_LORA);
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    
    LoRa.setSPIFrequency(1E6);
    LoRa.setSpreadingFactor(7);
    LoRa.setSignalBandwidth(125E3);
    LoRa.setCodingRate4(5);
    LoRa.setSyncWord(0x12);

    if (!LoRa.begin(915E6)) {
      Serial.println("❌ LoRa.begin() failed!");
      while (1);
    }
    Serial.println("✅ LoRa Transceiver Ready!");
  
}

void loop() {
    int windadcValue = analogRead(windSensorPin); 
    float windvoltage = (windadcValue / (float)adcResolution) * voltageRef; // 计算实际电压
    float windSpeed = windvoltage*1000* 0.027; // 根据手册公式计算风速
    Serial.print("wind ADC: ");
    Serial.print(windadcValue);
    Serial.print(" | voltage: ");
    Serial.print(windvoltage, 3);
    Serial.print(" V | wind speed: ");
    Serial.print(windSpeed, 2);
    Serial.println(" m/s");


    float V_ADC_135 = ads.readADC_SingleEnded(0) * (4.096 / 32767.0);
    float RS_135 = RL * ((5.0 / V_ADC_135) - 1);
    float ppm_135 = a_135 * pow((RS_135 / R0_135), b_135) * 100;

    float V_ADC_2 = ads.readADC_SingleEnded(1) * (4.096 / 32767.0);
    float RS_2 = RL * ((5.0 / V_ADC_2) - 1);
    float ppm_2 =  a_135 * pow((RS_2 / R0_2), b_135) * 100; // Smoke ppm

    float V_ADC_7 = ads.readADC_SingleEnded(2) * (4.096 / 32767.0);
    float RS_7 = RL * ((5.0 / V_ADC_7) - 1);
    float ppm_7 = a_7 * pow(RS_7 / R0_7, b_7);

    float V_ADC_9 = ads.readADC_SingleEnded(3) * (4.096 / 32767.0);
    float RS_9 = RL * ((5.0 / V_ADC_9) - 1);
    float ppm_9 = pow(10, (-2.3 * log10(RS_9 / R0_9) + 0.75));

    Serial.print("MQ-135 (CO2): "); Serial.print(ppm_135); Serial.println(" ppm");
    Serial.print("MQ-2 (Smoke): "); Serial.print(ppm_2); Serial.println(" ppm");
    Serial.print("MQ-7 (CO): "); Serial.print(ppm_7); Serial.println(" ppm");
    Serial.print("MQ-9 (Flammable Gas): "); Serial.print(ppm_9); Serial.println(" ppm");

    float temperature = dht.readTemperature();  // 读取摄氏度
    float humidity = dht.readHumidity();       // 读取湿度

    if (!isnan(temperature) && !isnan(humidity)) {
        Serial.print("Temperature: ");
        Serial.print(temperature);
        Serial.print(" *C | Humidity: ");
        Serial.print(humidity);
        Serial.println(" %");
    } else {
        Serial.println("Failed to read from DHT11 sensor!");
    } 

   
    while (SerialBT.available()) {  // 只要有数据，就一直读取
        while (SerialBT.available()) {
          char c = SerialBT.read();
          receivedData += c;

          if (receivedData.endsWith("<END>")) {
            break;
          }
        }
      

        // 跳过第一条数据，防止不完整
      if (!firstDataIgnored) {
        firstDataIgnored = true;
        receivedData="";
            continue;  
        }

      receivedData.trim();
      if (receivedData.startsWith("<START>") && receivedData.endsWith("<END>")) {
        String extractedData = receivedData.substring(7, receivedData.length() - 5);
        

            // 解析 Fire 和 NoFire 概率

        int fireIndex = extractedData.indexOf("Fire Probability: ");
        int noFireIndex = extractedData.indexOf("No Fire Probability: ");       
        if (fireIndex != -1 && noFireIndex != -1) {

            int fireStart = fireIndex + 18;  // "Fire Probability: " 长度是18
            int noFireStart = noFireIndex + 22;  // "No Fire Probability: " 长度是22
            String fireValue = extractedData.substring(fireStart, noFireIndex);
            fireValue.trim();  // 先获取字符串，再执行 trim()

            String noFireValue = extractedData.substring(noFireStart);
            noFireValue.trim();  // 先获取字符串，再执行 trim()

        // 截取数值部分

        Serial.println("Fire: " + fireValue);
        Serial.println("No Fire: " + noFireValue);
        clearBluetoothBuffer();
        receivedData = "";
        break;  // 解析完一条完整数据后退出 while 循环，执行其他任务
            }

        } else {
            Serial.println("drop worng data: " +   String(receivedData));
        }
    }
    String fireValue = "11";
    String payload = "{";
    payload += "\"fire_prob\":" + fireValue + ",";
    payload += "\"wind_speed\":" + String(windSpeed, 2) + ",";
    payload += "\"mq135\":" + String(ppm_135, 2) + ",";
    payload += "\"mq2\":" + String(ppm_2, 2) + ",";
    payload += "\"mq7\":" + String(ppm_7, 2) + ",";
    payload += "\"mq9\":" + String(ppm_9, 2);
    payload += "}";
    if (millis() - lastSendTime > sendInterval) {
      String message = "Hello from ESP32! " + String(millis() / 1000) + "s";
      Serial.print("Sending: ");
      Serial.println(payload);

      LoRa.beginPacket();
      LoRa.print(payload);
      LoRa.endPacket();

      lastSendTime = millis();
    }

    delay(5000);
}



void clearBluetoothBuffer() {
    while (SerialBT.available()) {
        SerialBT.read();  // 读取并丢弃缓冲区中的数据
    }
}
void connectToESP32CAM() {
    int maxRetries = 1;
    int retryCount = 0;

    Serial.println("🔍 正在搜索 ESP32-CAM_BT...");

    while (!SerialBT.connect("ESP32-CAM_BT") && retryCount < maxRetries) {  
        Serial.println("⚠️ 连接失败，重试中...");
        retryCount++;
        delay(2000);  // 2 秒后重试
    }

    if (SerialBT.connected()) {
        Serial.println("✅ 已成功连接到 ESP32-CAM!");
    } else {
        Serial.println("❌ 无法连接到 ESP32-CAM, 将继续其他任务...");
    }
}