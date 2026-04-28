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
import re
import subprocess
import sys
import threading
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
MOTOR_MAX_SPEED = float(os.getenv("MOTOR_MAX_SPEED", "0.25"))
MOTOR_RAMP_STEP = max(0.001, float(os.getenv("MOTOR_RAMP_STEP", "0.02")))
MOTOR_RAMP_INTERVAL = max(0.001, float(os.getenv("MOTOR_RAMP_INTERVAL", "0.01")))
MOTOR_DIRECTION_DEADTIME = max(0.0, float(os.getenv("MOTOR_DIRECTION_DEADTIME", "0.05")))
SERVO_MAX_OUTPUT = max(0.0, min(1.0, float(os.getenv("SERVO_MAX_OUTPUT", "0.25"))))
SERVO_DETACH_ON_NEUTRAL = os.getenv("SERVO_DETACH_ON_NEUTRAL", "0").strip().lower() in ("1", "true", "yes", "on")
SERVO_UPDATE_EPSILON = float(os.getenv("SERVO_UPDATE_EPSILON", "0.005"))
STEERING_INVERTED = os.getenv("STEERING_INVERTED", "0").strip().lower() in ("1", "true", "yes", "on")
DEBUG_CONTROLLER = os.getenv("DEBUG_CONTROLLER", "0").strip().lower() in ("1", "true", "yes", "on")

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
    "motion",
    "sensor",
    "accelerometer",
    "gyro",
)

DISCONNECT_BUTTON_COMBOS = tuple(
    combo
    for combo in (
        frozenset(
            code
            for code in (
                getattr(ecodes, "BTN_MODE", None),   # PS-Taste
                getattr(ecodes, "BTN_START", None),  # Options
            )
            if code is not None
        ),
        frozenset(
            code
            for code in (
                getattr(ecodes, "BTN_SELECT", None), # Create/Share
                getattr(ecodes, "BTN_START", None),  # Options
            )
            if code is not None
        ),
    )
    if len(combo) == 2
)

MAC_ADDRESS_PATTERN = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")


class ControllerDisconnectRequested(Exception):
    pass


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
motor_target_speed = 0.0
motor_current_speed = 0.0
motor_last_direction = 0
motor_deadtime_until = 0.0
motor_lock = threading.Lock()
motor_stop_event = threading.Event()


def speed_to_direction(speed: float) -> int:
    if speed > 0:
        return 1
    if speed < 0:
        return -1
    return 0


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
    value = (clamped / MAX_STEER_ANGLE) * SERVO_MAX_OUTPUT

    # Neutral aktiv halten. detach() kann bei RC-Lenkservos dazu fuehren,
    # dass die Lenkung nach einiger Zeit nicht mehr zuverlaessig anspricht.
    if abs(value) < 0.02:
        if SERVO_DETACH_ON_NEUTRAL:
            servo.detach()
        else:
            servo.value = 0.0
        last_servo_value = 0.0
        return

    # Nur aktualisieren, wenn sich der Wert merklich geändert hat
    if abs(value - last_servo_value) < SERVO_UPDATE_EPSILON:
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

def apply_motor(speed: float):
    """
    Schreibt den bereits begrenzten Geschwindigkeitswert direkt auf den Treiber.
    Diese Funktion enthält keine Ramp- oder Sicherheitslogik.
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


def motor_worker():
    global motor_current_speed, motor_last_direction, motor_deadtime_until

    while not motor_stop_event.is_set():
        now = time.monotonic()

        with motor_lock:
            target_speed = motor_target_speed

        target_direction = speed_to_direction(target_speed)
        current_direction = speed_to_direction(motor_current_speed)

        if (
            target_direction != 0 and
            current_direction != 0 and
            target_direction != current_direction
        ):
            motor_current_speed = 0.0
            apply_motor(0.0)
            motor_last_direction = 0
            motor_deadtime_until = now + MOTOR_DIRECTION_DEADTIME
            time.sleep(MOTOR_RAMP_INTERVAL)
            continue

        if now < motor_deadtime_until:
            apply_motor(0.0)
            time.sleep(MOTOR_RAMP_INTERVAL)
            continue

        if abs(target_speed - motor_current_speed) > MOTOR_RAMP_STEP:
            motor_current_speed += MOTOR_RAMP_STEP if target_speed > motor_current_speed else -MOTOR_RAMP_STEP
        else:
            motor_current_speed = target_speed

        apply_motor(motor_current_speed)
        motor_last_direction = speed_to_direction(motor_current_speed)
        time.sleep(MOTOR_RAMP_INTERVAL)


motor_thread = threading.Thread(target=motor_worker, name="motor-worker", daemon=True)
motor_thread.start()


def set_motor(speed: float):
    """
    Setzt die Zielgeschwindigkeit. Die eigentliche Ausgabe auf den
    Motortreiber übernimmt der Worker mit Soft-Ramp und Dead-Time.
    """
    global motor_target_speed

    speed = max(-MOTOR_MAX_SPEED, min(MOTOR_MAX_SPEED, speed))
    with motor_lock:
        motor_target_speed = speed


# =========================
# NOT-STOP
# =========================

def emergency_stop():
    """
    Stoppt sofort:
    - Motor
    - Servo (deaktiviert)
    """
    global motor_target_speed, motor_current_speed, motor_last_direction, motor_deadtime_until
    with motor_lock:
        motor_target_speed = 0.0
    motor_current_speed = 0.0
    motor_last_direction = 0
    motor_deadtime_until = 0.0
    apply_motor(0.0)
    set_servo(0.0)


# =========================
# CONTROLLER ABMELDUNG
# =========================

def is_disconnect_combo_pressed(pressed_keys):
    return any(combo <= pressed_keys for combo in DISCONNECT_BUTTON_COMBOS)


def get_controller_bluetooth_address(dev):
    for value in (getattr(dev, "uniq", ""), getattr(dev, "phys", "")):
        match = MAC_ADDRESS_PATTERN.search(str(value))
        if match:
            return match.group(0)
    return ""


def disconnect_controller(dev):
    emergency_stop()
    bluetooth_address = get_controller_bluetooth_address(dev)

    if not bluetooth_address:
        print("Keine Bluetooth-Adresse gefunden, beende nur die lokale Steuerung.")
        return

    print(f"Trenne Controller per Bluetooth: {bluetooth_address}")

    try:
        subprocess.run(
            ["bluetoothctl", "disconnect", bluetooth_address],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception as exc:
        print(f"Bluetooth-Trennung fehlgeschlagen: {exc}")


# =========================
# ACHSEN / TRIGGER KALIBRIERUNG
# =========================

def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def get_abs_info(dev, code):
    try:
        return dev.absinfo(code)
    except Exception:
        return None


def build_trigger_calibration(dev, code):
    """
    Manche Controller melden Trigger losgelassen als 0, andere als 255.
    Wir verwenden den Wert beim Verbinden als Neutralpunkt und berechnen
    daraus die richtige Richtung.
    """
    info = get_abs_info(dev, code)
    if info is None:
        return {
            "min": 0,
            "max": 255,
            "neutral": 0,
            "inverted": False,
        }

    raw_min = info.min
    raw_max = info.max
    neutral = info.value
    mid = raw_min + ((raw_max - raw_min) / 2)

    return {
        "min": raw_min,
        "max": raw_max,
        "neutral": neutral,
        "inverted": neutral >= mid,
    }


def build_axis_calibration(dev, code):
    """
    Kalibriert Analogsticks anhand der vom Kernel gemeldeten Achsdaten.
    PS5-Controller koennen je nach Treiber 0..255 oder -32768..32767 liefern.
    Wichtig: Fuer Sticks darf nicht der aktuelle Startwert als Mitte genutzt
    werden, weil der beim Verbinden kurz falsch sein kann.
    """
    info = get_abs_info(dev, code)
    if info is None:
        return {
            "min": 0,
            "max": 255,
            "center": 128,
        }

    raw_min = info.min
    raw_max = info.max
    center = raw_min + ((raw_max - raw_min) / 2)

    return {
        "min": raw_min,
        "max": raw_max,
        "center": center,
    }


def normalize_axis(raw_value: int, calibration) -> float:
    center = calibration["center"]

    if raw_value >= center:
        span = max(1, calibration["max"] - center)
        return clamp((raw_value - center) / span, -1.0, 1.0)

    span = max(1, center - calibration["min"])
    return clamp((raw_value - center) / span, -1.0, 1.0)


def normalize_trigger(raw_value: int, calibration) -> float:
    raw_min = calibration["min"]
    raw_max = calibration["max"]
    neutral = calibration["neutral"]

    if calibration["inverted"]:
        span = max(1, neutral - raw_min)
        return clamp((neutral - raw_value) / span)

    span = max(1, raw_max - neutral)
    return clamp((raw_value - neutral) / span)


def print_trigger_calibration(label: str, calibration):
    direction = "invertiert" if calibration["inverted"] else "normal"
    print(
        f"{label}: min={calibration['min']} "
        f"neutral={calibration['neutral']} "
        f"max={calibration['max']} "
        f"richtung={direction}"
    )


def print_axis_calibration(label: str, calibration):
    print(
        f"{label}: min={calibration['min']} "
        f"center={calibration['center']} "
        f"max={calibration['max']} "
        f"invertiert={STEERING_INVERTED}"
    )


def log_trigger_value(label: str, raw_value: int, normalized: float):
    if not DEBUG_CONTROLLER:
        return
    print(f"{label}: raw={raw_value} norm={normalized:.3f}")


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
            dev = InputDevice(CONTROLLER_DEVICE_PATH)
            capabilities = dev.capabilities()
            if is_controller_device(dev, capabilities):
                return dev
            print(
                f"Controller-Pfad ignoriert, ist kein Gamepad: "
                f"{dev.name} ({CONTROLLER_DEVICE_PATH})"
            )
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

        steering_calibration = build_axis_calibration(gamepad, ecodes.ABS_X)
        l2_calibration = build_trigger_calibration(gamepad, ecodes.ABS_Z)
        r2_calibration = build_trigger_calibration(gamepad, ecodes.ABS_RZ)
        print_axis_calibration("Lenkung ABS_X", steering_calibration)
        print_trigger_calibration("L2", l2_calibration)
        print_trigger_calibration("R2", r2_calibration)

        l2 = 0.0
        r2 = 0.0
        pressed_keys = set()

        try:
            # Event Loop für Controller
            for event in gamepad.read_loop():

                if event.type == ecodes.EV_KEY:
                    if event.value:
                        pressed_keys.add(event.code)
                    else:
                        pressed_keys.discard(event.code)

                    if is_disconnect_combo_pressed(pressed_keys):
                        print("Controller-Abmeldung erkannt: PS+Options oder Create+Options.")
                        disconnect_controller(gamepad)
                        raise ControllerDisconnectRequested

                    continue

                if event.type != ecodes.EV_ABS:
                    continue

                # Linker Stick (Lenkung)
                if event.code == ecodes.ABS_X:
                    norm = normalize_axis(event.value, steering_calibration)
                    if STEERING_INVERTED:
                        norm = -norm

                    if abs(norm) < DEADZONE_STICK:
                        norm = 0.0

                    set_servo(norm * MAX_STEER_ANGLE)

                # Trigger links (Rückwärts)
                elif event.code == ecodes.ABS_Z:
                    l2 = normalize_trigger(event.value, l2_calibration)
                    log_trigger_value("L2", event.value, l2)

                # Trigger rechts (Vorwärts)
                elif event.code == ecodes.ABS_RZ:
                    r2 = normalize_trigger(event.value, r2_calibration)
                    log_trigger_value("R2", event.value, r2)

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

        except ControllerDisconnectRequested:
            print("Controller-Steuerung beendet.")
            break

        finally:
            # Sicherheitsabschaltung
            emergency_stop()


# =========================
# STARTPUNKT
# =========================

if __name__ == "__main__":
    try:
        main()
    finally:
        motor_stop_event.set()
        apply_motor(0.0)
