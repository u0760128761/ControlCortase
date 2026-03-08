# ControlCortase — Control de Motores por Bluetooth

Esta aplicación controla dos motores de CC en una Raspberry Pi mediante Bluetooth (RFCOMM/SPP).

## Arquitectura
- **Aplicación Android**: Kotlin. Escanea y conecta dispositivos BT, envía comandos a motores.
- **Raspberry Pi**: Python (`motor_server.py`). Recibe comandos y controla los pines GPIO.

## Configuración de Raspberry Pi

### Hardware
- Raspberry Pi 3 B+ (o compatible con Bluetooth)
- Driver L298N, 2x Motor DC, Batería externa

**Cableado por defecto:**
- Motor 1: ENA=BCM25, IN1=BCM23, IN2=BCM24
- Motor 2: ENB=BCM18, IN3=BCM17, IN4=BCM27

### Software
1. Instalar dependencias:
   ```bash
   sudo apt-get update && sudo apt-get install python3-pip python3-rpi.gpio libbluetooth-dev
   pip3 install pybluez
   ```
2. Habilitar modo de compatibilidad Bluetooth — añadir flag `-C` a `bluetoothd`.
3. Hacer Pi detectable mediante `bluetoothctl`.
4. Ejecutar: `python3 motor_server.py`

## Configuración de Android
1. Abrir la carpeta `android/` en Android Studio.
2. Compilar e instalar en un dispositivo Android con Bluetooth.
3. En el primer inicio, conceder permisos de "Nearby Devices" / "Ubicación".

## Uso
1. Iniciar `motor_server.py` en la Pi.
2. Abrir la app → tocar Escanear (icono 🔍).
3. Seleccionar su Raspberry Pi de la lista.
4. Controlar motores con el D-Pad. El control deslizante ajusta la velocidad.

## Comandos (Protocolo)
Se envían como cadenas ASCII terminadas en `\n`:
- `FORWARD`, `BACKWARD`, `LEFT`, `RIGHT`, `STOP`
- `SPEED:<0-255>`
- `GET_CONFIG`, `UPDATE`, `RESTART`

## Controles de la Interfaz
- **Idioma** (icono de bandera): Cambiar entre Español / Inglés / Ruso.
- **Ayuda** (icono ?): Abre esta documentación.
- **Escanear** (icono de búsqueda): Escanea dispositivos Bluetooth emparejados.
- **Admin** (icono de engranaje): Actualizar firmware, reiniciar Pi, configurar pines y WiFi.
