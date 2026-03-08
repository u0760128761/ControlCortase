# ControlCortase — ROS2 Humble Workspace

> **Платформа:** Raspberry Pi 3 B+ · Ubuntu 22.04 · ROS2 Humble

Этот workspace заменяет монолитный `motor_server.py` на модульную ROS2-архитектуру,
совместимую с Navigation2, SLAM и LiDAR-интеграцией.

---

## Архитектура

```
Android App (Bluetooth)
        │  RFCOMM / ASCII протокол
        ▼
┌─────────────────────────────┐
│  bluetooth_bridge_node      │  controlcortase_bluetooth_bridge
│  - RFCOMM сервер (PyBluez)  │
│  - Парсинг ASCII команд     │
│  - Публикация /cmd_vel      │
└──────────────┬──────────────┘
               │  geometry_msgs/Twist
               ▼
┌─────────────────────────────┐
│  motor_controller_node      │  controlcortase_motor
│  - Подписка /cmd_vel        │
│  - Diff-drive конвертация   │
│  - GPIO/PWM → L298N         │
│  - Watchdog 500 мс          │
└─────────────────────────────┘
               │
               ▼
         GPIO (BCM)
    L298N Motor Driver
```

### Пакеты

| Пакет | Узел | Описание |
|---|---|---|
| `controlcortase_motor` | `motor_controller_node` | GPIO/PWM управление моторами |
| `controlcortase_bluetooth_bridge` | `bluetooth_bridge_node` | Bluetooth → ROS2 мост |
| `controlcortase_bringup` | — | Launch файл и конфигурация |

---

## Установка

### 1. Установка ROS2 Humble

```bash
# Добавить репозиторий ROS2
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt update
sudo apt install -y ros-humble-ros-base python3-colcon-common-extensions
```

### 2. Установка зависимостей Python

```bash
sudo apt install -y python3-rpi.gpio
pip3 install pybluez
```

> **Если `pybluez` не собирается:**
> ```bash
> sudo apt install -y libbluetooth-dev
> pip3 install pybluez
> ```

### 3. Настройка Bluetooth

```bash
# Включить режим совместимости для PyBluez
sudo nano /etc/systemd/system/bluetooth.service
# Добавить -C к ExecStart: ExecStart=/usr/lib/bluetooth/bluetoothd -C
sudo systemctl daemon-reload && sudo systemctl restart bluetooth

# Сделать Pi обнаруживаемым
bluetoothctl << 'EOF'
power on
discoverable on
pairable on
agent on
default-agent
EOF
```

---

## Сборка Workspace

```bash
cd ~/controlcortase_ws

# Установить ROS2 окружение
source /opt/ros/humble/setup.bash

# Разрешить зависимости
rosdep install --from-paths src --ignore-src -r -y

# Собрать все пакеты
colcon build --symlink-install

# Применить установленное окружение
source install/setup.bash
```

---

## Запуск

### Полный запуск системы

```bash
source /opt/ros/humble/setup.bash
source ~/controlcortase_ws/install/setup.bash

ros2 launch controlcortase_bringup controlcortase_bringup.launch.py
```

### Только управление моторами (без Bluetooth, для тестирования)

```bash
ros2 launch controlcortase_bringup controlcortase_bringup.launch.py use_bluetooth:=false
```

### С пользовательским файлом параметров

```bash
ros2 launch controlcortase_bringup controlcortase_bringup.launch.py \
  params_file:=/path/to/my_params.yaml
```

---

## Тестирование

### Отправка команды через /cmd_vel

```bash
# Движение вперёд
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"

# Поворот
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 1.0}}"

# СТОП
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}"
```

### Мониторинг

```bash
# Просмотр /cmd_vel
ros2 topic echo /cmd_vel

# Диагностика моторов
ros2 topic echo /diagnostics

# Список узлов
ros2 node list

# Параметры узла
ros2 param list /controlcortase/motor_controller_node
ros2 param get /controlcortase/motor_controller_node ena_pin
```

---

## Конфигурация (params.yaml)

Файл `config/params.yaml` содержит все параметры системы:

```yaml
motor_controller_node:
  ros__parameters:
    ena_pin: 25        # Enable M1 (BCM)
    in1_pin: 23        # IN1 направление (BCM)
    in2_pin: 24        # IN2 направление (BCM)
    enb_pin: 18        # Enable M2 (BCM)
    in3_pin: 17        # IN3 направление (BCM)
    in4_pin: 27        # IN4 направление (BCM)
    pwm_frequency: 1000.0
    max_linear_speed: 1.0
    max_angular_speed: 1.0
    watchdog_timeout_ms: 500

bluetooth_bridge_node:
  ros__parameters:
    max_linear_speed: 0.5
    max_angular_speed: 1.0
    bt_channel: 1
    reconnect_delay_s: 2.0
```

---

## Совместимость и расширение

| Функция | Статус |
|---|---|
| Navigation2 (Nav2) | ✅ Совместим через `/cmd_vel` |
| SLAM (slam_toolbox) | 🔧 Добавьте LiDAR-узел |
| WiFi Bridge | 🔧 Замените BT узел на UDP/WebSocket мост |
| LiDAR (RPLIDAR/Hokuyo) | 🔧 Добавьте `ros-humble-rplidar-ros` |
| Odometry | 🔧 Добавьте энкодеры в `motor_controller_node` |
| Battery Monitor | 🔧 Заглушка готова — добавьте ADC |

---

## Автозапуск при старте системы (systemd)

```bash
sudo nano /etc/systemd/system/controlcortase.service
```

```ini
[Unit]
Description=ControlCortase ROS2 Robot
After=network.target bluetooth.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
EnvironmentFile=/opt/ros/humble/setup.sh
Environment="ROS_DOMAIN_ID=42"
ExecStart=/bin/bash -c "source /home/pi/controlcortase_ws/install/setup.bash && \
  ros2 launch controlcortase_bringup controlcortase_bringup.launch.py"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable controlcortase
sudo systemctl start controlcortase
sudo systemctl status controlcortase
```
