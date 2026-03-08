# Миграция: motor_server.py → ROS2 архитектура

Этот документ описывает, как новая ROS2 архитектура заменяет
монолитный `motor_server.py`.

---

## Сравнение архитектур

### До (motor_server.py)

```
motor_server.py (монолит)
├── Bluetooth RFCOMM сервер
├── HTTP Flask веб-интерфейс
├── GPIO управление моторами
├── Watchdog логика
├── Конфигурация устройств
└── WebSocket логи
```

**Проблемы:**
- Одиночная точка отказа
- Нет стандартного интерфейса управления
- Невозможно интегрировать Navigation2 / SLAM
- Тяжело тестировать отдельные компоненты
- Жёсткая связь BT ↔ GPIO

---

### После (ROS2)

```
controlcortase_ws/
├── bluetooth_bridge_node    ← только Bluetooth + парсинг
│   └── публикует /cmd_vel
└── motor_controller_node    ← только GPIO/PWM
    └── подписывается /cmd_vel
```

**Преимущества:**
- Независимые узлы, независимые отказы
- `/cmd_vel` — стандарт Nav2, ROS2, RViz2
- Любой источник (BT, WiFi, Nav2, клавиатура) → управление
- `rqt`, `ros2 topic echo` — бесплатная отладка
- Watchdog в каждом узле независимо

---

## Маппинг команд

| Старый протокол | Новый ROS2 |
|---|---|
| `M1_FORWARD\n` | `Twist(linear.x=+0.5)` на `/cmd_vel` |
| `M1_BACKWARD\n` | `Twist(linear.x=-0.5)` на `/cmd_vel` |
| `M2_FORWARD\n` | `Twist(angular.z=+1.0)` на `/cmd_vel` |
| `M2_BACKWARD\n` | `Twist(angular.z=-1.0)` на `/cmd_vel` |
| `M1_STOP\n` | `Twist(linear.x=0)` |
| `M2_STOP\n` | `Twist(angular.z=0)` |
| `STOP\n` | `Twist()` (нулевой) |
| `SPEED:128\n` | Масштаб скорости 50% применяется к следующим Twist |
| `FORWARD\n` | `Twist(linear.x=+scale)` |
| `BACKWARD\n` | `Twist(linear.x=-scale)` |
| `LEFT\n` | `Twist(angular.z=+scale)` |
| `RIGHT\n` | `Twist(angular.z=-scale)` |
| `RESTART\n` | `ros2 lifecycle set ...` (будущая версия) |
| `UPDATE\n` | systemd / ansible (будущая версия) |

---

## Функционал motor_server.py не вошедший в ROS2 узлы

| Функция | Статус | Альтернатива |
|---|---|---|
| Flask веб-интерфейс | ❌ Убран | `ros2 topic pub`, RViz2, rqt |
| WebSocket терминал | ❌ Убран | `ros2 topic echo /rosout` |
| HC-SR04 дальномер | 🔧 Не реализован | Добавьте `ros-humble-sensor-msgs` + GPIO опрос |
| Конфигурация пинов на лету | 🔧 Параметры ROS2 | `ros2 param set ...` |
| WiFi настройки | ❌ Убран | `nmcli`, NetworkManager |
| Логирование в браузер | ❌ Убран | `rqt_console`, `ros2 topic echo /rosout` |

---

## Checklist миграции

- [x] Bluetooth RFCOMM сервер → `bluetooth_bridge_node`
- [x] ASCII протокол → `CommandParser` → `geometry_msgs/Twist`
- [x] GPIO L298N управление → `MotorDriver` + `MotorControllerNode`
- [x] Watchdog timeout → таймер ROS2 в `motor_controller_node`
- [x] Параметры пинов → `params.yaml` (ROS2 parameters)
- [x] Диагностика → `/diagnostics` topic
- [x] Аварийный стоп → `destroy_node()` + try/finally
- [ ] HC-SR04 датчик (TODO: отдельный узел)
- [ ] Одометрия (TODO: энкодеры)
- [ ] Веб-UI (TODO: rosbridge_suite + roslibjs)

---

## Android приложение

Android-часть проекта **не требует изменений** для базовой работы.
Оно по-прежнему отправляет те же ASCII команды по Bluetooth.

`bluetooth_bridge_node` полностью совместим со старым протоколом
и отвечает ACK-сообщениями в том же формате.

Для расширенных возможностей (статус Nav2, карта SLAM и т.д.)
рекомендуется заменить RFCOMM на **rosbridge_suite** + WebSocket.
