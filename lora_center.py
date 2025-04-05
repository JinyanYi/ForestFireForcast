import RPi.GPIO as GPIO
import time
from SX127x.LoRa import LoRa
from SX127x.board_config import BOARD
from SX127x.constants import MODE
import json
import requests  # Add requests library for HTTP requests

# Flask server address
FLASK_SERVER_URL = "http://192.168.2.90:50000/api/sensors/"

# Sensor ID mapping, please replace with actual Firebase assigned IDs
SENSOR_IDS = {
    "mq135": "-OMZ52hULVlcWp1HjY_3",      # MQ135_CO2
    "mq2": "-OMZ5FRWYXmtZDwXTIGk",        # MQ2_Smoke
    "mq7": "-OMZ5H08E2DKCTkymTxS",        # MQ7_CO
    "mq9": "-OMZ5JIY7Ap7CyNTOwSY",        # MQ9_Flammable
    "temperature": "-OMZ5LVfac6SqXCeQRW-", # Temperature
    "humidity": "-OMZ5Mnv-R5fWNH3v4Vl",    # Humidity
    "wind_speed": "-OMZ5OO8U2upkMfXPwWQ",  # Wind_Speed
    "fire_prob": "-OMZ5SCV9iN5PHStzJMR"    # Fire_Probability
}

# ---- Force RESET HIGH ----
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

RESET_PIN = 25
NSS_PIN = 8

GPIO.setup(RESET_PIN, GPIO.OUT)
GPIO.output(RESET_PIN, GPIO.HIGH)

GPIO.setup(NSS_PIN, GPIO.OUT)
GPIO.output(NSS_PIN, GPIO.HIGH)  # Ensure NSS idle HIGH

# ---- LoRa Setup ----
BOARD.setup()

class LoRaSelfPing(LoRa):
    def __init__(self, verbose=False):
        super(LoRaSelfPing, self).__init__(verbose)
        self.set_dio_mapping([1, 0, 0, 0, 0, 0])  # DIO0 for TX_DONE

lora = LoRaSelfPing(verbose=False)
lora.set_freq(915.0)
lora.set_spreading_factor(7)
lora.set_bw(7)
lora.set_coding_rate(5)
lora.set_preamble(8)
lora.set_sync_word(0x12)
lora.set_pa_config(pa_select=1)  # PA_BOOST

print("Self-ping test ready!")

def send_sensor_data_to_server(data):
    """Send sensor data to Flask server"""
    print(f"Sending data to Flask server: {FLASK_SERVER_URL}")
    
    try:
        # Send individual PUT requests for each sensor
        if "mq135" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["mq135"], 
                json={"value": data["mq135"]},
                timeout=5
            )
            print(f"MQ135 data send status: {response.status_code}")
            
        if "mq2" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["mq2"], 
                json={"value": data["mq2"]},
                timeout=5
            )
            print(f"MQ2 data send status: {response.status_code}")
            
        if "mq7" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["mq7"], 
                json={"value": data["mq7"]},
                timeout=5
            )
            print(f"MQ7 data send status: {response.status_code}")
            
        if "mq9" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["mq9"], 
                json={"value": data["mq9"]},
                timeout=5
            )
            print(f"MQ9 data send status: {response.status_code}")
            
        if "temperature" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["temperature"], 
                json={"value": data["temperature"]},
                timeout=5
            )
            print(f"Temperature data send status: {response.status_code}")
            
        if "humidity" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["humidity"], 
                json={"value": data["humidity"]},
                timeout=5
            )
            print(f"Humidity data send status: {response.status_code}")
            
        if "wind_speed" in data:
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["wind_speed"], 
                json={"value": data["wind_speed"]},
                timeout=5
            )
            print(f"Wind speed data send status: {response.status_code}")
            
        # Special handling for fire_prob parameter, ensure -1 value is correctly sent
        if "fire_prob" in data:
            # Send even if value is -1, which means camera is disconnected
            response = requests.put(
                FLASK_SERVER_URL + SENSOR_IDS["fire_prob"], 
                json={"value": data["fire_prob"]},
                timeout=5
            )
            
            # Print camera status information
            if data["fire_prob"] == -1:
                print("⚠️ Camera disconnected, fire detection status: Unknown")
            else:
                status = "Safe"
                if data["fire_prob"] >= 70:
                    status = "High Risk"
                elif data["fire_prob"] >= 50:
                    status = "Medium Risk"
                elif data["fire_prob"] >= 20:
                    status = "Low Risk"
                print(f"🔍 Fire detection status: {status} ({data['fire_prob']}%)")
            
            print(f"Fire probability data send status: {response.status_code}")
            
        print("All data sent successfully")
        
    except Exception as e:
        print(f"Error sending data: {e}")
        # No retry attempt, just report the error

try:
    while True:
        # RECEIVE phase
        lora.set_dio_mapping([0, 0, 0, 0, 0, 0])  # DIO0 for RX_DONE
        lora.set_mode(MODE.RXCONT)
        print("Listening for esp32...")
        reg_val = BOARD.spi.xfer2([0x01 & 0x7F, 0x00])
        print("RegOpMode now reads:", hex(reg_val[1]))

        rx_timeout = time.time() + 3
        while time.time() < rx_timeout:
            irq_flags = lora.get_irq_flags()
            if irq_flags.get('rx_done'):
                payload = lora.read_payload(nocheck=True)
                msg = ''.join([chr(b) for b in payload])
                print("🎉 Received:", msg)
                try:
                    data = json.loads(msg)
                    print("Parsed JSON:", data)
                    # Send data to Flask server
                    send_sensor_data_to_server(data)
                except json.JSONDecodeError:
                    print("❗ Received data is not valid JSON")
                lora.clear_irq_flags()
                break
            time.sleep(0.1)
        else:
            print("❌ RX timeout.")
        
        time.sleep(5)

except KeyboardInterrupt:
    print("Exiting lora_center.")
    lora.set_mode(MODE.SLEEP)
    BOARD.teardown()
