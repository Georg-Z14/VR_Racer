#!/usr/bin/env python3
# ======================================================
# 🎮 control_sender.py – Liest USB-Lenkrad & Pedale, sendet per Funk
# ======================================================
from RF24 import RF24
from inputs import get_gamepad
import struct
import time

# NRF24L01 Setup
radio = RF24(22, 0)
address = b"CAR01"

print("🚀 Initialisiere Funkmodul...")
radio.begin()
radio.setPALevel(3)
radio.setDataRate(1)
radio.openWritingPipe(address)
radio.stopListening()
print("✅ Funk-Sender bereit.")

# Standardwerte
speed = 0
steering = 90

def map_range(value, in_min, in_max, out_min, out_max):
    return int((value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

print("🎮 Warte auf Eingaben vom Lenkrad...")
while True:
    try:
        events = get_gamepad()
        for e in events:
            # Bei Logitech/Thrustmaster meist:
            # ABS_X = Lenkrad, ABS_Z oder ABS_RZ = Gas/Bremse
            if e.code == "ABS_X":
                steering = map_range(e.state, 0, 65535, 0, 180)
            elif e.code in ("ABS_Z", "ABS_RZ"):
                speed = map_range(e.state, 0, 65535, 0, 255)

            payload = struct.pack("BB", speed, steering)
            radio.write(payload)
            print(f"➡️ speed={speed:3d} steering={steering:3d}")

        time.sleep(0.02)
    except KeyboardInterrupt:
        print("\n🛑 Beendet.")
        break
    except Exception as e:
        print("⚠️", e)
        time.sleep(0.1)