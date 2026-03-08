# ControlCortase — Android Bluetooth Motor Control

This app controls two DC motors on a Raspberry Pi via Bluetooth (RFCOMM/SPP).

## Architecture
- **Android App**: Kotlin. Scans & connects to BT devices, sends motor commands.
- **Raspberry Pi**: Python (`motor_server.py`). Receives commands, controls GPIO.

## Raspberry Pi Setup

### Hardware
- Raspberry Pi 3 B+ (or Bluetooth-capable)
- L298N Motor Driver, 2x DC Motors, Battery Pack

**Default Wiring:**
- Motor 1: ENA=BCM25, IN1=BCM23, IN2=BCM24
- Motor 2: ENB=BCM18, IN3=BCM17, IN4=BCM27

### Software
1. Install dependencies:
   ```bash
   sudo apt-get update && sudo apt-get install python3-pip python3-rpi.gpio libbluetooth-dev
   pip3 install pybluez
   ```
2. Enable Bluetooth Compatibility Mode — add `-C` flag to `bluetoothd` in service file.
3. Make Pi discoverable via `bluetoothctl`.
4. Run: `python3 motor_server.py`

## Android Setup
1. Open `android/` in Android Studio.
2. Build & deploy to a Bluetooth-enabled Android device.
3. Grant "Nearby Devices" / "Location" permissions on first launch.

## Usage
1. Start `motor_server.py` on Pi.
2. Open App → tap Scan (🔍 icon).
3. Select your Raspberry Pi.
4. Use D-Pad to control motors. Slider adjusts speed.

## Commands (Protocol)
Sent as ASCII strings ending with `\n`:
- `FORWARD`, `BACKWARD`, `LEFT`, `RIGHT`, `STOP`
- `SPEED:<0-255>`
- `GET_CONFIG`, `UPDATE`, `RESTART`

## Controls
- **Language** (flag icon): Switch between English / Russian / Spanish.
- **Help** (? icon): Open this documentation.
- **Scan** (search icon): Scan for paired Bluetooth devices.
- **Admin** (gear icon): Update firmware, restart Pi, configure pins, WiFi settings.
