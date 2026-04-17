#!/usr/bin/env python3
"""
RC-Car Steuerung (stabile Version).

Verbesserungen:
- Ruhiger Servo durch angepasste Pulsbreite, Filtering und Smoothing
- Servo wird bei Neutralstellung deaktiviert
- Controller-Erkennung generisch ueber Analogachsen
- Automatische Auswahl fuer systemd-Autostart
- Statusdatei, damit der Controller-Zustand schnell pruefbar ist
- Sauberes Cleanup bei Abbruch
"""

import os
import sys
import time

from evdev import InputDevice, ecodes, list_devices
from gpiozero import OutputDevice, PWMOutputDevice, Servo
from gpiozero.pins.lgpio import LGPIOFactory


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Konstanten / Einstellungen
MAX_STEER_ANGLE = 25.0
DEADZONE_STICK = 0.08
DEADZONE_TRIGGER = 0.05

SERVO_PIN = 18
MOTOR_IN1 = 17
MOTOR_IN2 = 27
MOTOR_ENA = 12
PWM_FREQUENCY = 1000

CONTROLLER_AUTO_SELECT = os.getenv("CONTROLLER_AUTO_SELECT", "1").lower() not in ("0", "false", "no", "off")
CONTROLLER_DEVICE_PATH = os.getenv("CONTROLLER_DEVICE_PATH", "").strip()
CONTROLLER_STATUS_FILE = os.getenv("CONTROLLER_STATUS_FILE", "/tmp/vr-racer-controller.status")


# GPIO Initialisierung
factory = LGPIOFactory()

servo = Servo(
    SERVO_PIN,
    pin_factory=factory,
    min_pulse_width=0.0008,
    max_pulse_width=0.0022,
)

IN1 = OutputDevice(MOTOR_IN1, pin_factory=factory)
IN2 = OutputDevice(MOTOR_IN2, pin_factory=factory)
ENA = PWMOutputDevice(MOTOR_ENA, pin_factory=factory, frequency=PWM_FREQUENCY)


last_servo_value = 0.0


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


def set_servo(angle_deg: float) -> None:
    """
    Setzt den Lenkwinkel des Servos mit Begrenzung, Filtering und Smoothing.
    In Neutralstellung wird das Servo deaktiviert, damit es nicht permanent
    gegen die Mitte arbeitet.
    """
    global last_servo_value

    clamped = max(-MAX_STEER_ANGLE, min(MAX_STEER_ANGLE, angle_deg))
    value = clamped / MAX_STEER_ANGLE

    if abs(value) < 0.02:
        servo.detach()
        last_servo_value = 0.0
        return

    if abs(value - last_servo_value) < 0.02:
        return

    step = 0.03
    current = last_servo_value

    while abs(value - current) > step:
        current += step if value > current else -step
        servo.value = current
        time.sleep(0.01)

    servo.value = value
    last_servo_value = value


def set_motor(speed: float) -> None:
    """Setzt Geschwindigkeit und Richtung des Motors."""
    speed = max(-1.0, min(1.0, speed))

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
    """Stoppt Motor und deaktiviert das Servo."""
    set_motor(0.0)
    servo.detach()


def describe_device(device: InputDevice) -> str:
    return f"{device.name} ({device.path})"


def device_score(device: InputDevice) -> int:
    name = (device.name or "").lower()
    score = 0
    if "dualsense" in name:
        score += 100
    if "wireless controller" in name:
        score += 80
    if "sony" in name or "playstation" in name:
        score += 60
    try:
        abs_codes = set(device.capabilities(absinfo=False).get(ecodes.EV_ABS, []))
    except OSError:
        return score
    if ecodes.ABS_X in abs_codes:
        score += 10
    if ecodes.ABS_Z in abs_codes:
        score += 10
    if ecodes.ABS_RZ in abs_codes:
        score += 10
    return score


def find_controller() -> InputDevice | None:
    """Sucht generisch nach Eingabegeraeten mit Analogachsen."""
    devices = []

    if CONTROLLER_DEVICE_PATH:
        try:
            return InputDevice(CONTROLLER_DEVICE_PATH)
        except OSError:
            print(f"Controller-Pfad nicht verfuegbar: {CONTROLLER_DEVICE_PATH}")

    for path in list_devices():
        try:
            device = InputDevice(path)
            capabilities = device.capabilities()
            if ecodes.EV_ABS in capabilities:
                devices.append(device)
        except Exception:
            continue

    if not devices:
        return None

    devices.sort(key=device_score, reverse=True)

    if len(devices) == 1 or CONTROLLER_AUTO_SELECT or not sys.stdin.isatty():
        selected = devices[0]
        if len(devices) > 1:
            print("Mehrere Eingabegeraete gefunden, Autostart nutzt:", describe_device(selected))
            for device in devices:
                print("  -", describe_device(device))
        return selected

    print("\nGefundene Eingabegeraete:")
    for i, device in enumerate(devices):
        print(f"{i}: {describe_device(device)}")

    while True:
        try:
            idx = int(input("Waehle Controller Nummer: "))
            return devices[idx]
        except Exception:
            print("Ungueltige Eingabe")


def handle_event(event, state: dict) -> None:
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
    print("=== RC-Car Steuerung (stabile Version) ===")
    print(f"Statusdatei: {CONTROLLER_STATUS_FILE}")
    emergency_stop()
    write_status("waiting", "Kein Controller verbunden")

    while True:
        gamepad = find_controller()

        if gamepad is None:
            print("Kein Controller gefunden...")
            write_status("waiting", "Kein Controller verbunden")
            emergency_stop()
            time.sleep(2)
            continue

        detail = describe_device(gamepad)
        print(f"Verbunden mit: {detail}")
        write_status("connected", detail)

        state = {"r2": 0.0, "l2": 0.0}

        try:
            for event in gamepad.read_loop():
                handle_event(event, state)

        except OSError:
            print("Controller getrennt")
            write_status("disconnected", detail)
            emergency_stop()
            time.sleep(1)
        except KeyboardInterrupt:
            print("Programm beendet")
            write_status("stopped", "Programm beendet")
            emergency_stop()
            break
        finally:
            emergency_stop()


if __name__ == "__main__":
    main()
