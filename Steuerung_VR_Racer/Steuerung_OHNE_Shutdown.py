#!/usr/bin/env python3
"""
RC-Car Steuerung mit Raspberry Pi 5 und PS5 DualSense Controller.

- Lenkung: Linker Analog-Stick X-Achse
- Vorwaerts: R2
- Rueckwaerts: L2
- Not-Stop: Programmende setzt Motor und Servo auf neutral

Hardware:
- Servo: GPIO 18
- L298N Motor-Treiber:
  - IN1: GPIO 17
  - IN2: GPIO 27
  - ENA: GPIO 12

Abhaengigkeiten: gpiozero, lgpio, evdev
"""

import os
import sys
import time
from select import select

from evdev import InputDevice, ecodes, list_devices
from gpiozero import OutputDevice, PWMOutputDevice, Servo
from gpiozero.pins.lgpio import LGPIOFactory


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Konstanten und Einstellungen
MAX_STEER_ANGLE = 25.0
DEADZONE_STICK = 0.08
DEADZONE_TRIGGER = 0.05
SERVO_SMOOTHING = float(os.getenv("SERVO_SMOOTHING", "0.45"))
SERVO_MIN_DELTA = float(os.getenv("SERVO_MIN_DELTA", "0.01"))
SERVO_CENTER_SNAP = float(os.getenv("SERVO_CENTER_SNAP", "0.03"))
CONTROLLER_STATUS_FILE = os.getenv("CONTROLLER_STATUS_FILE", "/tmp/vr-racer-controller.status")
CONTROLLER_STATUS_INTERVAL = float(os.getenv("CONTROLLER_STATUS_INTERVAL", "5"))

SERVO_PIN = 18
MOTOR_IN1 = 17
MOTOR_IN2 = 27
MOTOR_ENA = 12
PWM_FREQUENCY = 1000
DUALSENSE_NAMES = ("dualsense", "wireless controller")


# GPIO Initialisierung
factory = LGPIOFactory()

servo = Servo(
    SERVO_PIN,
    pin_factory=factory,
    min_pulse_width=0.0008,
    max_pulse_width=0.0022
)

IN1 = OutputDevice(MOTOR_IN1, pin_factory=factory)
IN2 = OutputDevice(MOTOR_IN2, pin_factory=factory)
ENA = PWMOutputDevice(MOTOR_ENA, pin_factory=factory, frequency=PWM_FREQUENCY)

_servo_value = 0.0
_motor_speed = 0.0


def write_status(state: str, detail: str = "") -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} | {state}"
    if detail:
        line += f" | {detail}"
    try:
        with open(CONTROLLER_STATUS_FILE, "w", encoding="utf-8") as status_file:
            status_file.write(line + "\n")
    except OSError:
        pass


def set_servo(angle_deg: float, immediate: bool = False) -> None:
    """Setzt den Lenkwinkel des Servos."""
    global _servo_value

    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, angle_deg))
    target_value = clamped / MAX_STEER_ANGLE

    if immediate:
        next_value = target_value
    else:
        next_value = _servo_value + (target_value - _servo_value) * SERVO_SMOOTHING
        if abs(target_value) < SERVO_CENTER_SNAP and abs(next_value) < SERVO_CENTER_SNAP:
            next_value = 0.0
        if abs(next_value - _servo_value) < SERVO_MIN_DELTA:
            return

    _servo_value = max(-1.0, min(1.0, next_value))
    servo.value = _servo_value


def set_motor(speed: float) -> None:
    """Setzt Motorgeschwindigkeit und Richtung ueber den L298N."""
    global _motor_speed

    speed = max(-1.0, min(1.0, speed))
    if abs(speed - _motor_speed) < 0.01:
        return
    _motor_speed = speed

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


def emergency_stop() -> None:
    """Sofortiger Not-Stop: Motor und Servo auf neutral."""
    global _motor_speed

    _motor_speed = 999.0
    set_motor(0.0)
    set_servo(0.0, immediate=True)


def find_dualsense() -> InputDevice | None:
    """Sucht nach einem angeschlossenen PS5 DualSense Controller."""
    for path in list_devices():
        try:
            device = InputDevice(path)
        except Exception:
            continue

        name = (device.name or "").lower()
        if any(controller_name in name for controller_name in DUALSENSE_NAMES):
            return device

    return None


def handle_controller_event(event, state: dict) -> None:
    if event.type != ecodes.EV_ABS:
        return

    if event.code == ecodes.ABS_X:
        norm = (event.value - 128) / 128.0
        if abs(norm) < DEADZONE_STICK:
            norm = 0.0
        set_servo(norm * MAX_STEER_ANGLE)

    elif event.code == ecodes.ABS_Z:
        state["l2"] = event.value / 255.0

    elif event.code == ecodes.ABS_RZ:
        state["r2"] = event.value / 255.0

    speed = state["r2"] - state["l2"]
    if abs(speed) < DEADZONE_TRIGGER:
        speed = 0.0

    set_motor(speed)


def main() -> None:
    print("=== RC-Car Steuerung - PS5 DualSense Edition ===")
    print(f"Lenkung: Linker Stick X (+/-{MAX_STEER_ANGLE} Grad)")
    print("Gas: R2 = Vorwaerts, L2 = Rueckwaerts")
    print(f"Statusdatei: {CONTROLLER_STATUS_FILE}")
    print("------------------------------------------------")

    emergency_stop()
    write_status("waiting", "Kein DualSense verbunden")

    while True:
        gamepad = find_dualsense()

        if gamepad is None:
            print("Kein DualSense gefunden - warte 2 Sekunden...")
            write_status("waiting", "Kein DualSense verbunden")
            emergency_stop()
            time.sleep(2)
            continue

        detail = f"{gamepad.name} | {gamepad.path}"
        print(f"Verbunden mit: {detail}")
        print("Druecke Strg+C zum Beenden")
        write_status("connected", detail)

        state = {"r2": 0.0, "l2": 0.0}
        last_status = time.monotonic()

        try:
            while True:
                ready, _, _ = select([gamepad.fd], [], [], 1.0)
                now = time.monotonic()

                if now - last_status >= CONTROLLER_STATUS_INTERVAL:
                    write_status("connected", detail)
                    last_status = now

                if not ready:
                    continue

                for event in gamepad.read():
                    handle_controller_event(event, state)

        except OSError:
            print("Controller-Verbindung verloren!")
            write_status("disconnected", detail)
            emergency_stop()
            time.sleep(1)
        except KeyboardInterrupt:
            print("Programm beendet per Strg+C")
            write_status("stopped", "Programm beendet")
            emergency_stop()
            break


if __name__ == "__main__":
    main()
