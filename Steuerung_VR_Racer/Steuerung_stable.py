#!/usr/bin/env python3
"""
RC-Car Steuerung (stabile Version)

Verbesserungen:
- Ruhiger Servo (angepasste Pulsbreite, Filtering, Smoothing)
- Servo wird bei Neutralstellung deaktiviert (detach)
- Controller-Erkennung generisch (keine feste Namenssuche)
- automatische Auswahl bei mehreren Eingabegeräten
- Sauberes Cleanup bei Abbruch
"""

import os
import sys
import time

from evdev import InputDevice, ecodes, list_devices
from gpiozero import OutputDevice, PWMOutputDevice, Servo
from gpiozero.pins.lgpio import LGPIOFactory


# UTF-8 Konfiguration für saubere Konsolenausgabe
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# =========================
# KONSTANTEN / EINSTELLUNGEN
# =========================

MAX_STEER_ANGLE = 25.0        # maximaler Lenkwinkel
DEADZONE_STICK = 0.08         # Totzone für Analogstick
DEADZONE_TRIGGER = 0.05       # Totzone für Trigger

SERVO_PIN = 18                # Servo GPIO
MOTOR_IN1 = 17                # Motor Richtung
MOTOR_IN2 = 27
MOTOR_ENA = 12                # PWM Geschwindigkeit

PWM_FREQUENCY = 1000          # PWM Frequenz für Motor
CONTROLLER_DEVICE_PATH = os.getenv("CONTROLLER_DEVICE_PATH", "").strip()

PREFERRED_CONTROLLER_NAMES = (
    "wireless controller",
    "dualsense",
    "dualshock",
    "playstation",
    "sony",
    "gamepad",
    "joystick",
)

IGNORED_DEVICE_NAMES = (
    "mouse",
    "keyboard",
    "touchpad",
    "touchscreen",
)


# =========================
# GPIO INITIALISIERUNG
# =========================

factory = LGPIOFactory()

# Servo mit stabiler Pulsbreite
servo = Servo(
    SERVO_PIN,
    pin_factory=factory,
    min_pulse_width=0.0008,
    max_pulse_width=0.0022,
)

# Motorsteuerung
IN1 = OutputDevice(MOTOR_IN1, pin_factory=factory)
IN2 = OutputDevice(MOTOR_IN2, pin_factory=factory)
ENA = PWMOutputDevice(MOTOR_ENA, pin_factory=factory, frequency=PWM_FREQUENCY)


# =========================
# GLOBALER STATUS
# =========================

last_servo_value = 0.0


# =========================
# SERVO STEUERUNG
# =========================

def set_servo(angle_deg: float):
    """
    Setzt den Lenkwinkel des Servos mit:
    - Begrenzung (Clamp)
    - Deadzone
    - Filtering (nur bei Änderung)
    - Smoothing (sanfte Bewegung)
    """

    global last_servo_value

    # Winkel begrenzen
    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, angle_deg))
    value = clamped / MAX_STEER_ANGLE

    # Wenn nahezu neutral -> Servo deaktivieren
    if abs(value) < 0.02:
        servo.detach()
        last_servo_value = 0.0
        return

    # Nur aktualisieren, wenn sich der Wert merklich geändert hat
    if abs(value - last_servo_value) < 0.02:
        return

    # Sanfte Bewegung (Smoothing)
    step = 0.03
    current = last_servo_value

    while abs(value - current) > step:
        current += step if value > current else -step
        servo.value = current
        time.sleep(0.01)

    # Zielwert setzen
    servo.value = value
    last_servo_value = value


# =========================
# MOTOR STEUERUNG
# =========================

def set_motor(speed: float):
    """
    Setzt die Geschwindigkeit und Richtung des Motors.
    - positive Werte: vorwärts
    - negative Werte: rückwärts
    - 0: Stop
    """

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


# =========================
# NOT-STOP
# =========================

def emergency_stop():
    """
    Stoppt sofort:
    - Motor
    - Servo (deaktiviert)
    """
    set_motor(0.0)
    servo.detach()


# =========================
# CONTROLLER ERKENNUNG
# =========================

def capability_codes(capabilities, event_type):
    """
    Liefert nur die numerischen evdev-Codes.
    EV_ABS kann je nach evdev-Version als (code, AbsInfo) geliefert werden.
    """
    codes = set()

    for item in capabilities.get(event_type, []):
        if isinstance(item, tuple):
            codes.add(item[0])
        else:
            codes.add(item)

    return codes


def is_controller_device(dev, capabilities):
    """
    Erlaubt nur Geräte, die zur erwarteten PS5/Gamepad-Belegung passen.
    Mäuse können ebenfalls EV_ABS melden und dürfen nicht als Controller gelten.
    """
    name = dev.name.lower()
    abs_codes = capability_codes(capabilities, ecodes.EV_ABS)
    key_codes = capability_codes(capabilities, ecodes.EV_KEY)

    gamepad_buttons = {
        getattr(ecodes, code_name)
        for code_name in (
            "BTN_GAMEPAD",
            "BTN_SOUTH",
            "BTN_EAST",
            "BTN_NORTH",
            "BTN_WEST",
            "BTN_TL",
            "BTN_TR",
            "BTN_TL2",
            "BTN_TR2",
            "BTN_SELECT",
            "BTN_START",
            "BTN_MODE",
        )
        if hasattr(ecodes, code_name)
    }

    has_controller_name = any(keyword in name for keyword in PREFERRED_CONTROLLER_NAMES)
    has_ignored_name = any(keyword in name for keyword in IGNORED_DEVICE_NAMES)
    has_gamepad_button = bool(key_codes & gamepad_buttons)

    has_steering_axis = ecodes.ABS_X in abs_codes
    has_trigger_axis = ecodes.ABS_Z in abs_codes or ecodes.ABS_RZ in abs_codes

    if has_ignored_name and not has_gamepad_button:
        return False

    return has_steering_axis and has_trigger_axis and (has_gamepad_button or has_controller_name)


def find_controller():
    """
    Sucht nach einem Gamepad/PS5-Controller mit passenden Analogachsen.
    Gibt:
    - direkt Gerät zurück (wenn nur eins gefunden)
    - automatische Auswahl (wenn mehrere vorhanden)
    """

    if CONTROLLER_DEVICE_PATH:
        try:
            return InputDevice(CONTROLLER_DEVICE_PATH)
        except Exception:
            print(f"Controller-Pfad nicht verfügbar: {CONTROLLER_DEVICE_PATH}")

    devices = []

    for path in list_devices():
        try:
            dev = InputDevice(path)
            capabilities = dev.capabilities()

            # Nur echte Gamepad-Kandidaten akzeptieren.
            if is_controller_device(dev, capabilities):
                devices.append(dev)

        except Exception:
            continue

    # Kein Gerät gefunden
    if not devices:
        return None

    # Nur ein Gerät -> direkt verwenden
    if len(devices) == 1:
        return devices[0]

    selected = devices[0]
    print(f"Mehrere Eingabegeräte gefunden, nutze automatisch: {selected.name} ({selected.path})")
    return selected


# =========================
# HAUPTPROGRAMM
# =========================

def main():
    print("=== RC-Car Steuerung (stabile Version) ===")

    # Beim Start alles neutral setzen
    emergency_stop()

    while True:
        gamepad = find_controller()

        # Kein Controller gefunden -> warten
        if gamepad is None:
            print("Kein Controller gefunden...")
            time.sleep(2)
            continue

        print(f"Verbunden mit: {gamepad.name}")

        r2 = 0.0
        l2 = 0.0

        try:
            # Event Loop für Controller
            for event in gamepad.read_loop():

                if event.type != ecodes.EV_ABS:
                    continue

                # Linker Stick (Lenkung)
                if event.code == ecodes.ABS_X:
                    norm = (event.value - 128) / 128.0

                    if abs(norm) < DEADZONE_STICK:
                        norm = 0.0

                    set_servo(norm * MAX_STEER_ANGLE)

                # Trigger links (Rückwärts)
                elif event.code == ecodes.ABS_Z:
                    l2 = event.value / 255.0

                # Trigger rechts (Vorwärts)
                elif event.code == ecodes.ABS_RZ:
                    r2 = event.value / 255.0

                # Geschwindigkeit berechnen
                speed = r2 - l2

                if abs(speed) < DEADZONE_TRIGGER:
                    speed = 0.0

                set_motor(speed)

        except OSError:
            print("Controller getrennt")
            emergency_stop()
            time.sleep(1)

        except KeyboardInterrupt:
            print("Programm beendet")
            emergency_stop()
            break

        finally:
            # Sicherheitsabschaltung
            emergency_stop()


# =========================
# STARTPUNKT
# =========================

if __name__ == "__main__":
    main()
