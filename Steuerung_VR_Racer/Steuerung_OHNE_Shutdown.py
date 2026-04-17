# 06.03.26 /7 Oliver / Denis

########################################################

# Alternativ Steuerungs Skript - OHNE SHUTDOWN

########################################################


#!/usr/bin/env python3
import os
import sys
import time
from gpiozero import Servo, PWMOutputDevice, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from evdev import InputDevice, ecodes, list_devices

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────
# GPIO SETUP
# ─────────────────────────────────────
factory = LGPIOFactory()

servo = Servo(
    18,
    pin_factory=factory,
    min_pulse_width=0.0010,
    max_pulse_width=0.0020
)

IN1 = OutputDevice(17, pin_factory=factory)
IN2 = OutputDevice(27, pin_factory=factory)
ENA = PWMOutputDevice(12, pin_factory=factory, frequency=1000)

# ─────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────
MAX_STEER_ANGLE = 25
DEADZONE_STICK = 0.08
DEADZONE_TRIGGER = 0.05
CONTROLLER_MAC = os.getenv("PS5_CONTROLLER_MAC", "").strip()
CONTROLLER_NAMES = (
    "dualsense",
    "wireless controller",
    "playstation",
    "sony interactive entertainment",
)
STEERING_AXIS = ecodes.ABS_X
L2_AXES = (ecodes.ABS_Z, ecodes.ABS_BRAKE)
R2_AXES = (ecodes.ABS_RZ, ecodes.ABS_GAS)

# ─────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────
def set_servo(angle_deg):
    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, float(angle_deg)))
    servo.value = clamped / MAX_STEER_ANGLE


def set_motor(speed):
    if speed > 0:
        IN1.on()
        IN2.off()
        ENA.value = min(1.0, speed)
    elif speed < 0:
        IN1.off()
        IN2.on()
        ENA.value = min(1.0, -speed)
    else:
        IN1.off()
        IN2.off()
        ENA.value = 0.0


def emergency_stop():
    set_motor(0.0)
    set_servo(0)


def normalize_mac(value):
    return (value or "").strip().lower().replace("-", ":")


def device_matches_mac(device):
    if not CONTROLLER_MAC:
        return True
    return normalize_mac(device.uniq) == normalize_mac(CONTROLLER_MAC)


def device_name_matches(device):
    name = (device.name or "").lower()
    return any(part in name for part in CONTROLLER_NAMES)


def device_has_controls(device):
    try:
        abs_codes = set(device.capabilities(absinfo=False).get(ecodes.EV_ABS, []))
    except OSError:
        return False
    return (
        STEERING_AXIS in abs_codes
        and any(axis in abs_codes for axis in L2_AXES)
        and any(axis in abs_codes for axis in R2_AXES)
    )


def describe_device(device):
    uniq = device.uniq or "keine MAC/uniq"
    return f"{device.path} | {device.name} | {uniq}"


def list_controller_candidates():
    devices = []
    for path in list_devices():
        try:
            device = InputDevice(path)
        except OSError:
            continue
        if device_name_matches(device) or device_has_controls(device):
            devices.append(device)
    return devices


def find_dualsense():
    candidates = []
    for path in list_devices():
        try:
            device = InputDevice(path)
        except OSError:
            continue

        if not device_matches_mac(device):
            continue

        if device_name_matches(device) and device_has_controls(device):
            return device

        if device_name_matches(device) or device_has_controls(device):
            candidates.append(device)

    for device in candidates:
        if device_has_controls(device):
            return device

    return None


# ─────────────────────────────────────
# MAIN CONTROL LOOP
# ─────────────────────────────────────
if __name__ == "__main__":

    print("=== RC CAR – PS5 FINAL VERSION ===")
    if CONTROLLER_MAC:
        print("Suche Controller mit MAC/uniq:", normalize_mac(CONTROLLER_MAC))
    emergency_stop()

    while True:

        gamepad = find_dualsense()

        if gamepad is None:
            print("Kein DualSense gefunden – warte...")
            candidates = list_controller_candidates()
            if candidates:
                print("Gefundene Controller-Kandidaten:")
                for device in candidates:
                    print("  -", describe_device(device))
            elif CONTROLLER_MAC:
                print("Kein Gerät mit dieser MAC/uniq gefunden.")
            emergency_stop()
            time.sleep(2)
            continue

        print("Verbunden mit:", describe_device(gamepad))

        r2 = 0.0
        l2 = 0.0

        try:
            for event in gamepad.read_loop():

                if event.type == ecodes.EV_ABS:

                    # Linker Stick X (0–255 → -1 bis +1)
                    if event.code == STEERING_AXIS:
                        norm = (event.value - 128) / 128
                        if abs(norm) < DEADZONE_STICK:
                            norm = 0.0
                        set_servo(norm * MAX_STEER_ANGLE)

                    # L2
                    elif event.code in L2_AXES:
                        l2 = event.value / 255

                    # R2
                    elif event.code in R2_AXES:
                        r2 = event.value / 255

                    # Motorberechnung
                    speed = r2 - l2
                    if abs(speed) < DEADZONE_TRIGGER:
                        speed = 0.0

                    set_motor(speed)

        except OSError:
            print("Controller getrennt!")
            emergency_stop()
            time.sleep(1)
