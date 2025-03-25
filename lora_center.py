import RPi.GPIO as GPIO
import time
from SX127x.LoRa import LoRa
from SX127x.board_config import BOARD
from SX127x.constants import MODE

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

try:
    while True:
        # SEND phase
        message = "Self-ping from Pi!"
        print("Sending:", message)
        lora.set_mode(MODE.STDBY)
        time.sleep(0.01)
        lora.write_payload([ord(c) for c in message])

        # ---- NSS Debug ----
        print("NSS state before manual TX force:", GPIO.input(NSS_PIN))

        # ---- Manual TX Mode Force ----
        BOARD.spi.xfer2([0x81, 0x83])  # RegOpMode = TX mode

        # ---- NSS Manual Release ----
        GPIO.output(NSS_PIN, GPIO.HIGH)
        time.sleep(0.01)
        print("NSS released (forced HIGH)")

        # Confirm RegOpMode
        reg_val = BOARD.spi.xfer2([0x01 & 0x7F, 0x00])
        print("RegOpMode now reads:", hex(reg_val[1]))

        # TX_DONE IRQ Wait
        send_timeout = time.time() + 3
        while time.time() < send_timeout:
            irq_flags = lora.get_irq_flags()
            if irq_flags.get('tx_done'):
                lora.clear_irq_flags()
                print("✅ Packet sent!")
                break
            time.sleep(0.1)
        else:
            print("❌ TX timeout! Still stuck mode.")
        
        time.sleep(0.5)

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
                print("🎉 Self-received:", msg)
                lora.clear_irq_flags()
                break
            time.sleep(0.1)
            data = json.loads(msg)
            
        else:
            print("❌ RX timeout.")
        
        time.sleep(5)

except KeyboardInterrupt:
    print("Exiting self-ping test.")
    lora.set_mode(MODE.SLEEP)
    BOARD.teardown()
