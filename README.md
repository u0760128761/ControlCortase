# ControlCortase - Android Bluetooth Motor Control

This project consists of an Android application and a Python script for Raspberry Pi to wirelessly control two DC motors (e.g., via L298N driver).

## Architecture

*   **Android App**: Kotlin-based application. Scans for Bluetooth devices, connects via RFCOMM (SPP), and provides a GUI to control motors.
*   **Raspberry Pi**: Python script running `RFCOMM` server. Listens for commands and controls GPIO pins.

## 1. Raspberry Pi Setup

### Hardware
*   Raspberry Pi 3 B+ (or compatible with Bluetooth).
*   L298N Motor Driver.
*   2x DC Motors.
*   Battery Pack for Motors (Do not power motors directly from Pi 5V if they are large).

**Wiring (Default in script):**
*   **Motor 1**: ENA=BCM25, IN1=BCM23, IN2=BCM24
*   **Motor 2**: ENB=BCM18, IN3=BCM17, IN4=BCM27
*   **Ground**: Connect Ground of L298N to Ground of Raspberry Pi.

### Software
1.  Install dependencies on Raspberry Pi:
    ```bash
    sudo apt-get update
    sudo apt-get install python3-pip python3-rpi.gpio libbluetooth-dev
    pip3 install pybluez
    ```
    *Note: If `pybluez` fails to build, ensure `libbluetooth-dev` is installed.*

2.  Enable Bluetooth Compatibility Mode (if experiencing connection issues):
    Edit `/etc/systemd/system/dbus-org.bluez.service`:
    ```ini
    ExecStart=/usr/lib/bluetooth/bluetoothd -C
    ```
    Reload daemon: `sudo systemctl daemon-reload && sudo systemctl restart bluetooth`

3.  Make Pi Discoverable:
    ```bash
    bluetoothctl
    > power on
    > discoverable on
    > pairable on
    > agent on
    > default-agent
    ```

4.  Run the Server:
    ```bash
    python3 motor_server.py
    ```

## 2. Android Setup

1.  Open the `android/` folder in Android Studio.
2.  Build the project.
3.  Deploy to an Android device (must have Bluetooth).
4.  **Permissions**: On first launch, grant "Nearby Devices" or "Location" permissions depending on Android version.

## 3. Usage
1.  Running `motor_server.py` on Pi.
2.  Open App -> Click "Scan Devices".
3.  Select your Raspberry Pi from the list.
4.  Wait for "Connected" status.
5.  Use buttons to control motors. Slider controls speed (PWM).

## Protocol
Commands are sent as ASCII strings ending with `\n`.
*   `M1_FORWARD`, `M1_BACKWARD`, `M1_STOP`
*   `M2_FORWARD`, `M2_BACKWARD`, `M2_STOP`
*   `SPEED:<0-255>`
