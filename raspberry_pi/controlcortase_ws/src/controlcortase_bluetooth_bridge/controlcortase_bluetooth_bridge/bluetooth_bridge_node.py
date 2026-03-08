#!/usr/bin/env python3
"""
Bluetooth RFCOMM → ROS2 мост для робота ControlCortase.

Запускает RFCOMM-сервер (PyBluez), принимает подключения Android-приложения,
парсит ASCII-протокол и публикует geometry_msgs/Twist в /cmd_vel.

ASCII протокол → Twist маппинг:
    M1_FORWARD   → linear.x  = +max_linear
    M1_BACKWARD  → linear.x  = -max_linear
    M2_FORWARD   → angular.z = +max_angular
    M2_BACKWARD  → angular.z = -max_angular
    M1_STOP      → linear.x  = 0
    M2_STOP      → angular.z = 0
    SPEED:<0-255> → масштабирование max_linear и max_angular

Безопасность: при отключении клиента публикуется нулевой Twist.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Twist

import threading
import socket
import time
import json
import subprocess
from typing import Optional

# Попытка импорта bluetooth (PyBluez)
try:
    import bluetooth
    BLUETOOTH_AVAILABLE = True
except ImportError:
    BLUETOOTH_AVAILABLE = False


class MockBluetooth:
    """Заглушка bluetooth для разработки на не-Pi системах."""

    @staticmethod
    def advertise_service(*args, **kwargs) -> None:
        pass

    @staticmethod
    def BluetoothSocket(*args) -> 'MockSocket':
        return MockSocket()

    RFCOMM = 'RFCOMM'
    PORT_ANY = 0
    SERIAL_PORT_CLASS = 'uuid:SERIAL_PORT_CLASS'
    SERIAL_PORT_PROFILE = 'profile:SERIAL_PORT_PROFILE'


class MockSocket:
    """Заглушка Bluetooth сокета."""

    def bind(self, addr) -> None:
        pass

    def listen(self, backlog: int) -> None:
        pass

    def accept(self):
        # Симуляция вечного ожидания
        time.sleep(9999)
        return self, ('00:00:00:00:00:00', 0)

    def recv(self, size: int) -> bytes:
        return b''

    def send(self, data: bytes) -> None:
        pass

    def close(self) -> None:
        pass

    def getsockname(self):
        return ('', 1)

    def settimeout(self, timeout) -> None:
        pass



# ---------------------------------------------------------------------------
# WiFi менеджер через nmcli
# ---------------------------------------------------------------------------

class WiFiManager:
    """
    Управление WiFi на Raspberry Pi через NetworkManager (nmcli).

    Требования на Pi:
        sudo apt install -y network-manager
        sudo systemctl enable NetworkManager
        sudo systemctl start NetworkManager

    Разрешение без sudo для пользователя (одноразово):
        sudo nano /etc/sudoers.d/ros-wifi
        # Добавить строку:
        # <username> ALL=(ALL) NOPASSWD: /usr/bin/nmcli
    """

    @staticmethod
    def _nmcli(*args: str, timeout: int = 15) -> tuple[int, str, str]:
        """
        Выполнить команду nmcli.

        Returns:
            Кортеж (returncode, stdout, stderr).
        """
        cmd = ['nmcli'] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, '', 'Timeout'
        except FileNotFoundError:
            return -1, '', 'nmcli not found — install network-manager'
        except Exception as e:
            return -1, '', str(e)

    @classmethod
    def get_status(cls) -> dict:
        """
        Получить текущий статус WiFi подключения.

        Returns:
            {"connected": bool, "ssid": str, "signal": int, "ip": str}
        """
        rc, out, err = cls._nmcli('-t', '-f', 'active,ssid,signal,bars', 'dev', 'wifi')
        if rc != 0:
            return {"connected": False, "error": err}

        for line in out.splitlines():
            parts = line.split(':')
            if len(parts) >= 2 and parts[0] == 'yes':
                ssid = parts[1] if len(parts) > 1 else 'Unknown'
                signal = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                # Получаем IP адрес
                _, ip_out, _ = cls._nmcli('-t', '-f', 'IP4.ADDRESS', 'con', 'show', '--active')
                ip = ip_out.split('\n')[0].replace('IP4.ADDRESS[1]:', '').split('/')[0].strip()
                return {
                    "connected": True,
                    "ssid": ssid,
                    "signal": signal,
                    "ip": ip,
                }

        return {"connected": False}

    @classmethod
    def scan_networks(cls) -> dict:
        """
        Сканирование доступных WiFi сетей.

        Returns:
            {"networks": [{"ssid": str, "signal": int, "security": str}]}
        """
        # Запуск принудительного сканирования
        cls._nmcli('dev', 'wifi', 'rescan', timeout=5)
        time.sleep(2)  # Дать время на сканирование

        rc, out, err = cls._nmcli(
            '-t', '-f', 'ssid,signal,security',
            'dev', 'wifi', 'list',
        )
        if rc != 0:
            return {"networks": [], "error": err}

        seen = set()
        networks = []
        for line in out.splitlines():
            parts = line.split(':')
            if len(parts) < 1:
                continue
            ssid = parts[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            signal = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            security = parts[2].strip() if len(parts) > 2 else 'Open'
            networks.append({
                "ssid": ssid,
                "signal": signal,
                "security": security if security else 'Open',
            })

        networks.sort(key=lambda n: n['signal'], reverse=True)
        return {"networks": networks}

    @classmethod
    def connect(cls, ssid: str, password: str) -> dict:
        """
        Подключиться к WiFi сети.

        Алгоритм:
        1. Удалить старое сохранённое соединение с этим SSID (если есть).
        2. Подключиться через nmcli (создаёт новый профиль).
        3. Проверить статус.

        Args:
            ssid: Имя сети.
            password: Пароль (пустой для открытых сетей).

        Returns:
            {"status": "connected"} или {"status": "error", "error": str}
        """
        # Удаление старого профиля с тем же SSID (если есть)
        cls._nmcli('con', 'delete', ssid, timeout=5)

        # Подключение
        if password:
            rc, out, err = cls._nmcli(
                'dev', 'wifi', 'connect', ssid,
                'password', password,
                timeout=30,
            )
        else:
            rc, out, err = cls._nmcli(
                'dev', 'wifi', 'connect', ssid,
                timeout=30,
            )

        if rc == 0:
            status = cls.get_status()
            if status.get('connected') and status.get('ssid') == ssid:
                return {"status": "connected", "ssid": ssid, "ip": status.get('ip', '')}
            else:
                return {"status": "connected", "ssid": ssid}  # nmcli сказал OK
        else:
            # Типичные причины ошибок nmcli
            error_msg = err or out
            if 'No network with SSID' in error_msg:
                error_msg = f'Сеть "{ssid}" не найдена. Выполните сканирование.'
            elif 'Secrets were required' in error_msg or 'password' in error_msg.lower():
                error_msg = 'Неверный пароль'
            elif 'timeout' in error_msg.lower():
                error_msg = 'Таймаут подключения'
            return {"status": "error", "error": error_msg}

    @classmethod
    def disconnect(cls) -> dict:
        """
        Отключиться от текущей WiFi сети.

        Returns:
            {"status": "disconnected"} или {"status": "error", "error": str}
        """
        rc, out, err = cls._nmcli('dev', 'disconnect', 'wlan0', timeout=10)
        if rc == 0:
            return {"status": "disconnected"}
        # Попробовать через wlan1 если wlan0 не найден
        rc2, _, _ = cls._nmcli('dev', 'disconnect', 'wlan1', timeout=10)
        if rc2 == 0:
            return {"status": "disconnected"}
        return {"status": "error", "error": err or out}


class CommandParser:
    """
    Парсер ASCII-команд устаревшего протокола ControlCortase.

    Хранит текущее состояние linear/angular скоростей и
    обновляет их при получении команд.
    """

    # Диапазон значений SPEED команды
    SPEED_MIN = 0
    SPEED_MAX = 255

    def __init__(
        self,
        max_linear_speed: float = 0.5,
        max_angular_speed: float = 1.0,
    ) -> None:
        """
        Инициализация парсера.

        Args:
            max_linear_speed: Максимальная линейная скорость (м/с).
            max_angular_speed: Максимальная угловая скорость (рад/с).
        """
        self._max_linear = max_linear_speed
        self._max_angular = max_angular_speed
        self._speed_scale = 0.5  # Начальный масштаб 50%

        # Текущие компоненты скорости
        self._linear_x: float = 0.0
        self._angular_z: float = 0.0

    def parse(self, command: str) -> Optional[Twist]:
        """
        Парсинг одной ASCII команды и обновление состояния.

        Args:
            command: Строка команды (без символа новой строки).

        Returns:
            Объект Twist если состояние изменилось, иначе None.
        """
        command = command.strip().upper()

        if not command:
            return None

        twist = Twist()

        if command == 'M1_FORWARD':
            self._linear_x = self._max_linear * self._speed_scale
            self._angular_z = 0.0
        elif command == 'M1_BACKWARD':
            self._linear_x = -self._max_linear * self._speed_scale
            self._angular_z = 0.0
        elif command == 'M2_FORWARD':
            self._linear_x = 0.0
            self._angular_z = self._max_angular * self._speed_scale
        elif command == 'M2_BACKWARD':
            self._linear_x = 0.0
            self._angular_z = -self._max_angular * self._speed_scale
        elif command in ('M1_STOP', 'M2_STOP', 'STOP', 'FORWARD_STOP', 'BACKWARD_STOP'):
            self._linear_x = 0.0
            self._angular_z = 0.0
        elif command == 'FORWARD':
            self._linear_x = self._max_linear * self._speed_scale
            self._angular_z = 0.0
        elif command == 'BACKWARD':
            self._linear_x = -self._max_linear * self._speed_scale
            self._angular_z = 0.0
        elif command == 'LEFT':
            self._linear_x = 0.0
            self._angular_z = self._max_angular * self._speed_scale
        elif command == 'RIGHT':
            self._linear_x = 0.0
            self._angular_z = -self._max_angular * self._speed_scale
        elif command == 'GET_CONFIG':
            # Информационная команда — не влияет на движение
            return None
        elif command.startswith('SPEED:'):
            return self._parse_speed(command)
        else:
            return None

        twist.linear.x = self._linear_x
        twist.angular.z = self._angular_z
        return twist

    def _parse_speed(self, command: str) -> Optional[Twist]:
        """
        Парсинг и применение команды SPEED:<0-255>.

        Args:
            command: Строка команды вида 'SPEED:128'.

        Returns:
            Twist с обновлёнными скоростями или None при ошибке.
        """
        try:
            parts = command.split(':')
            if len(parts) != 2:
                return None

            speed_raw = int(parts[1])
            speed_raw = max(self.SPEED_MIN, min(self.SPEED_MAX, speed_raw))

            # Масштабирование: 0-255 → 0.0-1.0
            self._speed_scale = speed_raw / self.SPEED_MAX

            # Применяем новый масштаб к текущему движению
            twist = Twist()
            if self._linear_x != 0.0:
                sign = 1.0 if self._linear_x > 0 else -1.0
                self._linear_x = sign * self._max_linear * self._speed_scale
            if self._angular_z != 0.0:
                sign = 1.0 if self._angular_z > 0 else -1.0
                self._angular_z = sign * self._max_angular * self._speed_scale

            twist.linear.x = self._linear_x
            twist.angular.z = self._angular_z
            return twist

        except (ValueError, IndexError):
            return None

    def get_zero_twist(self) -> Twist:
        """Возвращает нулевой Twist для аварийной остановки."""
        self._linear_x = 0.0
        self._angular_z = 0.0
        return Twist()


class BluetoothBridgeNode(Node):
    """
    ROS2 узел — мост между Bluetooth RFCOMM и /cmd_vel.

    Архитектура:
    - Основной поток ROS2: spin() и публикация Twist.
    - Фоновый поток Bluetooth: приём данных из сокета.
    - Thread-safe очередь сообщений между потоками.
    - Перепубликация через ROS2 таймер (избегает блокировок).
    """

    # UUID профиля Serial Port (SPP) для Bluetooth
    BT_UUID = '94f39d29-7d6d-437d-973b-fba39e49d4ee'
    BT_SERVICE_NAME = 'ControlCortase Motor Bridge'

    def __init__(self) -> None:
        super().__init__('bluetooth_bridge_node')

        # Объявление параметров
        self._declare_parameters()

        # Загрузка параметров
        params = self._load_parameters()

        # Thread-safe буфер для последнего Twist
        self._twist_lock = threading.Lock()
        self._pending_twist: Optional[Twist] = None
        self._client_connected = False

        # Инициализация парсера команд
        self._parser = CommandParser(
            max_linear_speed=params['max_linear_speed'],
            max_angular_speed=params['max_angular_speed'],
        )

        # QoS для управления
        cmd_vel_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Публикатор /cmd_vel
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', cmd_vel_qos)

        # Таймер публикации (10 Гц) — публикует накопленный Twist в потоке ROS2
        self._publish_timer = self.create_timer(0.1, self._publish_timer_callback)

        # Bluetooth сокеты
        self._server_socket: Optional[object] = None
        self._client_socket: Optional[object] = None

        # Флаг завершения работы
        self._shutdown_event = threading.Event()

        # Запуск Bluetooth потока
        self._bt_thread = threading.Thread(
            target=self._bluetooth_server_loop,
            name='bt-rfcomm-server',
            daemon=True,
        )
        self._bt_thread.start()

        self.get_logger().info(
            f'bluetooth_bridge_node запущен. '
            f'PyBluez={BLUETOOTH_AVAILABLE}, '
            f'max_linear={params["max_linear_speed"]}, '
            f'max_angular={params["max_angular_speed"]}'
        )

    def _declare_parameters(self) -> None:
        """Объявление параметров узла."""
        self.declare_parameter('max_linear_speed', 0.5)
        self.declare_parameter('max_angular_speed', 1.0)
        self.declare_parameter('bt_channel', 1)
        self.declare_parameter('bt_service_name', self.BT_SERVICE_NAME)
        self.declare_parameter('reconnect_delay_s', 2.0)

    def _load_parameters(self) -> dict:
        """Загрузка параметров из ROS2 Parameter Server."""
        return {
            'max_linear_speed': self.get_parameter('max_linear_speed').value,
            'max_angular_speed': self.get_parameter('max_angular_speed').value,
            'bt_channel': self.get_parameter('bt_channel').value,
            'bt_service_name': self.get_parameter('bt_service_name').value,
            'reconnect_delay_s': self.get_parameter('reconnect_delay_s').value,
        }

    def _bluetooth_server_loop(self) -> None:
        """
        Основной цикл Bluetooth сервера (в отдельном потоке).
        Обрабатывает подключение, приём данных и переподключение.
        """
        bt_module = bluetooth if BLUETOOTH_AVAILABLE else MockBluetooth

        while not self._shutdown_event.is_set():
            try:
                self._accept_and_serve(bt_module)
            except Exception as e:
                if not self._shutdown_event.is_set():
                    self.get_logger().error(f'Ошибка Bluetooth сервера: {e}')
                self._handle_disconnect()

            if not self._shutdown_event.is_set():
                delay = self.get_parameter('reconnect_delay_s').value
                self.get_logger().info(f'Переподключение через {delay:.1f} сек...')
                self._shutdown_event.wait(timeout=delay)

    def _accept_and_serve(self, bt_module) -> None:
        """
        Принятие подключения и обслуживание клиента.

        Args:
            bt_module: Модуль bluetooth или его заглушка.
        """
        # Создание серверного сокета
        self._server_socket = bt_module.BluetoothSocket(bt_module.RFCOMM)
        self._server_socket.bind(('', self.get_parameter('bt_channel').value))
        self._server_socket.listen(1)

        port = self._server_socket.getsockname()[1]

        # Регистрация SDP-сервиса (для совместимости с Android)
        if BLUETOOTH_AVAILABLE:
            bluetooth.advertise_service(
                self._server_socket,
                self.get_parameter('bt_service_name').value,
                service_id=self.BT_UUID,
                service_classes=[self.BT_UUID, bluetooth.SERIAL_PORT_CLASS],
                profiles=[bluetooth.SERIAL_PORT_PROFILE],
            )

        self.get_logger().info(
            f'Ожидание Bluetooth подключения на канале {port}... '
            f'(UUID: {self.BT_UUID})'
        )

        # Принятие входящего подключения
        self._client_socket, client_info = self._server_socket.accept()
        self._client_socket.settimeout(1.0)

        self._client_connected = True
        client_addr = client_info[0] if isinstance(client_info, tuple) else str(client_info)
        self.get_logger().info(f'Клиент подключён: {client_addr}')

        # Приветственное сообщение
        self._send_ack('CONNECTED:ControlCortase_ROS2')

        # Основной цикл приёма данных
        self._receive_loop()

    def _receive_loop(self) -> None:
        """Цикл приёма и парсинга данных от клиента."""
        buffer = ''

        while not self._shutdown_event.is_set() and self._client_connected:
            try:
                data = self._client_socket.recv(1024)

                if not data:
                    # Клиент закрыл соединение
                    self.get_logger().info('Клиент закрыл соединение.')
                    break

                buffer += data.decode('utf-8', errors='ignore')

                # Обработка всех полных команд (разделитель — '\n')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    self._process_command(line.strip())

            except OSError:
                # Таймаут recv — нормально, продолжаем ожидание
                continue
            except Exception as e:
                if not self._shutdown_event.is_set():
                    self.get_logger().error(f'Ошибка приёма данных: {e}')
                break

    def _process_command(self, command: str) -> None:
        """
        Обработка одной команды: парсинг и передача Twist в ROS2 поток.

        Args:
            command: Строка команды из ASCII протокола.
        """
        if not command:
            return

        self.get_logger().debug(f'Получена команда: "{command}"')

        twist = self._parser.parse(command)

        if twist is not None:
            # Thread-safe запись Twist для публикации в ROS2 потоке
            with self._twist_lock:
                self._pending_twist = twist

            # ACK подтверждение
            self._send_ack(f'OK:{command}')
        else:
            # Специальные команды без движения
            if command.upper() == 'GET_CONFIG':
                self._send_ack('CONFIG:ROS2_BRIDGE:READY')
            elif command.upper() == 'WIFI_STATUS':
                self._handle_wifi_status()
            elif command.upper() == 'WIFI_SCAN':
                self._handle_wifi_scan()
            elif command.upper().startswith('WIFI_CONNECT:'):
                payload = command[len('WIFI_CONNECT:'):].strip()
                self._handle_wifi_connect(payload)
            elif command.upper() == 'WIFI_DISCONNECT':
                self._handle_wifi_disconnect()
            else:
                self.get_logger().warn(f'Неизвестная команда: "{command}"')
                self._send_ack(f'ERR:UNKNOWN:{command}')

    def _send_json(self, data: dict) -> None:
        """
        Отправка JSON-ответа клиенту (с символом новой строки).

        Args:
            data: Словарь для сериализации в JSON.
        """
        if self._client_socket is not None:
            try:
                payload = json.dumps(data, ensure_ascii=False) + '\n'
                self._client_socket.send(payload.encode('utf-8'))
            except Exception as e:
                self.get_logger().debug(f'Не удалось отправить JSON: {e}')

    def _handle_wifi_status(self) -> None:
        """Ответить JSON с текущим статусом WiFi подключения."""
        self.get_logger().info('WIFI_STATUS: запрашиваю статус...')
        status = WiFiManager.get_status()
        self._send_json(status)
        self.get_logger().info(f'WIFI_STATUS: {status}')

    def _handle_wifi_scan(self) -> None:
        """Сканировать сети и ответить JSON списком."""
        self.get_logger().info('WIFI_SCAN: начинаю сканирование...')
        result = WiFiManager.scan_networks()
        self._send_json(result)
        self.get_logger().info(f'WIFI_SCAN: найдено {len(result.get("networks", []))} сетей')

    def _handle_wifi_connect(self, payload: str) -> None:
        """
        Подключиться к WiFi сети.

        Args:
            payload: JSON строка вида '{"ssid": "...", "password": "..."}'
        """
        try:
            data = json.loads(payload)
            ssid = data.get('ssid', '').strip()
            password = data.get('password', '').strip()

            if not ssid:
                self._send_json({'status': 'error', 'error': 'SSID не указан'})
                return

            self.get_logger().info(f'WIFI_CONNECT: подключаюсь к "{ssid}"...')
            result = WiFiManager.connect(ssid, password)
            self._send_json(result)
            self.get_logger().info(f'WIFI_CONNECT: результат={result}')

        except json.JSONDecodeError as e:
            self.get_logger().error(f'WIFI_CONNECT: ошибка парсинга JSON: {e}')
            self._send_json({'status': 'error', 'error': f'Неверный формат команды: {e}'})

    def _handle_wifi_disconnect(self) -> None:
        """Отключиться от текущей WiFi сети."""
        self.get_logger().info('WIFI_DISCONNECT: отключаюсь...')
        result = WiFiManager.disconnect()
        self._send_json(result)
        self.get_logger().info(f'WIFI_DISCONNECT: результат={result}')

    def _send_ack(self, message: str) -> None:
        """
        Отправка ACK-сообщения клиенту (текстовый формат).

        Args:
            message: Строка подтверждения.
        """
        if self._client_socket is not None:
            try:
                self._client_socket.send(f'{message}\n'.encode('utf-8'))
            except Exception as e:
                self.get_logger().debug(f'Не удалось отправить ACK: {e}')

    def _handle_disconnect(self) -> None:
        """Обработка отключения клиента — публикация нулевого Twist."""
        if self._client_connected:
            self.get_logger().warn(
                'Bluetooth клиент отключён — публикую нулевой Twist (СТОП)'
            )
            # Аварийная остановка
            with self._twist_lock:
                self._pending_twist = self._parser.get_zero_twist()

        self._client_connected = False

        # Закрытие сокетов
        for sock_attr in ('_client_socket', '_server_socket'):
            sock = getattr(self, sock_attr, None)
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
                setattr(self, sock_attr, None)

    def _publish_timer_callback(self) -> None:
        """
        Таймер публикации (выполняется в потоке ROS2).
        Безопасно извлекает Twist из буфера и публикует его.
        """
        with self._twist_lock:
            twist = self._pending_twist
            self._pending_twist = None

        if twist is not None:
            self._cmd_vel_pub.publish(twist)
            self.get_logger().debug(
                f'Опубликован Twist: lin={twist.linear.x:.2f}, ang={twist.angular.z:.2f}'
            )

    def destroy_node(self) -> None:
        """Корректное завершение узла с остановкой Bluetooth потока."""
        self.get_logger().info('Завершение bluetooth_bridge_node...')

        # Сигнал завершения Bluetooth потоку
        self._shutdown_event.set()

        # Публикация нулевого Twist перед выходом
        try:
            self._cmd_vel_pub.publish(Twist())
        except Exception:
            pass

        # Закрытие сокетов
        self._handle_disconnect()

        # Ожидание завершения потока
        if self._bt_thread.is_alive():
            self._bt_thread.join(timeout=3.0)

        super().destroy_node()


def main(args=None) -> None:
    """Точка входа узла bluetooth_bridge_node."""
    rclpy.init(args=args)
    node = None

    try:
        node = BluetoothBridgeNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if node:
            node.get_logger().fatal(f'Критическая ошибка: {e}')
        raise
    finally:
        if node:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
