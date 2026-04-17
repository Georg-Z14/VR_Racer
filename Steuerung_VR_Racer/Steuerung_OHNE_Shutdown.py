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

import sys
import time

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

SERVO_PIN = 18
MOTOR_IN1 = 17
MOTOR_IN2 = 27
MOTOR_ENA = 12
PWM_FREQUENCY = 1000


# GPIO Initialisierung
factory = LGPIOFactory()

servo = Servo(
    SERVO_PIN,
    pin_factory=factory,
    min_pulse_width=0.0010,
    max_pulse_width=0.0020,
)

IN1 = OutputDevice(MOTOR_IN1, pin_factory=factory)
IN2 = OutputDevice(MOTOR_IN2, pin_factory=factory)
ENA = PWMOutputDevice(MOTOR_ENA, pin_factory=factory, frequency=PWM_FREQUENCY)


def set_servo(angle_deg: float) -> None:
    """Setzt den Lenkwinkel des Servos."""
    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, angle_deg))
    servo.value = clamped / MAX_STEER_ANGLE


def set_motor(speed: float) -> None:
    """Setzt Motorgeschwindigkeit und Richtung ueber den L298N."""
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
    set_motor(0.0)
    set_servo(0.0)


def find_dualsense() -> InputDevice | None:
    """Sucht nach einem angeschlossenen PS5 DualSense Controller."""
    for path in list_devices():
        try:
            device = InputDevice(path)
        except Exception:
            continue

        name = device.name or ""
        if "DualSense" in name or "Wireless Controller" in name:
            return device

    return None


def main() -> None:
    print("=== RC-Car Steuerung - PS5 DualSense Edition ===")
    print(f"Lenkung: Linker Stick X (+/-{MAX_STEER_ANGLE} Grad)")
    print("Gas: R2 = Vorwaerts, L2 = Rueckwaerts")
    print("------------------------------------------------")

    emergency_stop()

    while True:
        gamepad = find_dualsense()

        if gamepad is None:
            print("Kein DualSense gefunden - warte 2 Sekunden...")
            emergency_stop()
            time.sleep(2)
            continue

        print(f"Verbunden mit: {gamepad.name}")
        print("Druecke Strg+C zum Beenden")

        r2 = 0.0
        l2 = 0.0

        try:
            for event in gamepad.read_loop():
                if event.type != ecodes.EV_ABS:
                    continue

                if event.code == ecodes.ABS_X:
                    norm = (event.value - 128) / 128.0
                    if abs(norm) < DEADZONE_STICK:
                        norm = 0.0
                    set_servo(norm * MAX_STEER_ANGLE)

                elif event.code == ecodes.ABS_Z:
                    l2 = event.value / 255.0

                elif event.code == ecodes.ABS_RZ:
                    r2 = event.value / 255.0

                speed = r2 - l2
                if abs(speed) < DEADZONE_TRIGGER:
                    speed = 0.0

                set_motor(speed)

        except OSError:
            print("Controller-Verbindung verloren!")
            emergency_stop()
            time.sleep(1)
        except KeyboardInterrupt:
            print("Programm beendet per Strg+C")
            emergency_stop()
            break


if __name__ == "__main__":
    main()
