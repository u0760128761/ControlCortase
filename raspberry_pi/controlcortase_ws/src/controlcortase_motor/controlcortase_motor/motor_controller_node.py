#!/usr/bin/env python3
"""
Узел управления моторами для робота ControlCortase.

Подписывается на /cmd_vel (geometry_msgs/Twist), конвертирует
команды в PWM-сигналы для моторных драйверов через GPIO Raspberry Pi.

Поддерживаемые драйверы (параметр motor_driver_type):
  - 'l298n'   — классический двойной H-мост (ENA/IN1/IN2, ENB/IN3/IN4)
  - 'bts7960' — мощный полумостовой драйвер BTS7960 (два чипа на мотор)
                Пины: R_PWM/L_PWM/R_EN/L_EN для каждого мотора.

Архитектура: дифференциальный привод (два независимых колеса).
Безопасность: watchdog 500 мс — при отсутствии команд моторы останавливаются.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Twist
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue

from abc import ABC, abstractmethod
from typing import Optional

# Попытка импорта RPi.GPIO — на не-Pi системах выводим предупреждение
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Заглушка GPIO (для разработки не на Raspberry Pi)
# ---------------------------------------------------------------------------

class MockGPIO:
    """Заглушка GPIO для разработки не на Raspberry Pi."""

    BCM = 'BCM'
    OUT = 'OUT'
    LOW = 0
    HIGH = 1

    @staticmethod
    def setmode(mode: str) -> None:
        pass

    @staticmethod
    def setwarnings(flag: bool) -> None:
        pass

    @staticmethod
    def setup(pin: int, mode: str) -> None:
        pass

    @staticmethod
    def output(pin: int, state: int) -> None:
        pass

    @staticmethod
    def cleanup() -> None:
        pass

    class PWM:
        def __init__(self, pin: int, frequency: float) -> None:
            self.pin = pin
            self.frequency = frequency

        def start(self, duty_cycle: float) -> None:
            pass

        def ChangeDutyCycle(self, duty_cycle: float) -> None:
            pass

        def stop(self) -> None:
            pass


# ---------------------------------------------------------------------------
# Абстрактный интерфейс драйвера мотора
# ---------------------------------------------------------------------------

class MotorDriverBase(ABC):
    """
    Абстрактный базовый класс для всех моторных драйверов.
    Определяет единый интерфейс независимо от типа железа.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._current_speed: float = 0.0

    @abstractmethod
    def set_speed(self, speed_normalized: float) -> None:
        """
        Установить скорость мотора.

        Args:
            speed_normalized: Скорость от -1.0 до +1.0.
                              +1.0 — максимум вперёд, -1.0 — назад, 0.0 — стоп.
        """

    @abstractmethod
    def stop(self) -> None:
        """Немедленная остановка мотора."""

    @abstractmethod
    def cleanup(self) -> None:
        """Освобождение ресурсов (PWM и GPIO)."""

    @property
    def current_speed(self) -> float:
        """Текущая нормализованная скорость мотора."""
        return self._current_speed

    @property
    def name(self) -> str:
        """Имя мотора."""
        return self._name


# ---------------------------------------------------------------------------
# Драйвер L298N
# ---------------------------------------------------------------------------

class L298NMotorDriver(MotorDriverBase):
    """
    Драйвер для классического двойного H-моста L298N.

    Схема управления одним мотором:
      ENA (Enable/PWM) — ШИМ сигнал скорости
      IN1 / IN2        — направление (HIGH/LOW или LOW/HIGH)

    Подключение к L298N:
      ENA → пин Enable (PWM способный)
      IN1 → пин IN1
      IN2 → пин IN2
    """

    def __init__(
        self,
        gpio: object,
        in1_pin: int,
        in2_pin: int,
        en_pin: int,
        pwm_frequency: float,
        name: str,
    ) -> None:
        """
        Инициализация драйвера L298N.

        Args:
            gpio: Модуль RPi.GPIO или его заглушка.
            in1_pin: Первый пин направления (BCM).
            in2_pin: Второй пин направления (BCM).
            en_pin: Пин Enable (PWM).
            pwm_frequency: Частота PWM в Гц.
            name: Имя мотора.
        """
        super().__init__(name)
        self._gpio = gpio
        self._in1 = in1_pin
        self._in2 = in2_pin

        gpio.setup(in1_pin, gpio.OUT)
        gpio.setup(in2_pin, gpio.OUT)
        gpio.setup(en_pin, gpio.OUT)

        self._pwm = gpio.PWM(en_pin, pwm_frequency)
        self._pwm.start(0)

    def set_speed(self, speed_normalized: float) -> None:
        speed_normalized = max(-1.0, min(1.0, speed_normalized))
        self._current_speed = speed_normalized

        if speed_normalized > 0.01:
            self._gpio.output(self._in1, self._gpio.HIGH)
            self._gpio.output(self._in2, self._gpio.LOW)
        elif speed_normalized < -0.01:
            self._gpio.output(self._in1, self._gpio.LOW)
            self._gpio.output(self._in2, self._gpio.HIGH)
        else:
            # Активное торможение
            self._gpio.output(self._in1, self._gpio.LOW)
            self._gpio.output(self._in2, self._gpio.LOW)

        self._pwm.ChangeDutyCycle(abs(speed_normalized) * 100.0)

    def stop(self) -> None:
        self._gpio.output(self._in1, self._gpio.LOW)
        self._gpio.output(self._in2, self._gpio.LOW)
        self._pwm.ChangeDutyCycle(0)
        self._current_speed = 0.0

    def cleanup(self) -> None:
        self._pwm.stop()


# ---------------------------------------------------------------------------
# Драйвер BTS7960
# ---------------------------------------------------------------------------

class BTS7960MotorDriver(MotorDriverBase):
    """
    Драйвер для высокотокового контроллера BTS7960 (43A IBT-2).

    Использует два чипа BTS7960 на мотор для формирования полного H-моста.
    Каждый чип управляет одним направлением через PWM пин.

    Схема управления одним мотором:
      RPWM  — ШИМ для движения вперёд (Right PWM, BTS7960 #1)
      LPWM  — ШИМ для движения назад  (Left PWM,  BTS7960 #2)
      R_EN  — Enable правого чипа (HIGH = активен)
      L_EN  — Enable левого чипа  (HIGH = активен)

    Преимущества перед L298N:
      - Ток до 43A (против 2A у L298N)
      - КПД ~98% (против ~70% у L298N)
      - Встроенная тепловая защита и защита от перегрузки
      - Не перегревается без радиатора при умеренных нагрузках

    Типичное подключение к Raspberry Pi:
      RPWM → GPIO пин с поддержкой PWM
      LPWM → GPIO пин с поддержкой PWM
      R_EN → любой GPIO
      L_EN → любой GPIO
      VCC  → 5V Pi
      GND  → GND Pi
      B+   → + аккумулятора мотора
      B-   → - аккумулятора мотора
      M+   → + мотора
      M-   → - мотора

    Режимы работы:
      Вперёд:  RPWM = PWM(%), LPWM = 0, R_EN = HIGH, L_EN = HIGH
      Назад:   RPWM = 0, LPWM = PWM(%), R_EN = HIGH, L_EN = HIGH
      Стоп:    RPWM = 0, LPWM = 0   (или R_EN = LOW, L_EN = LOW)
    """

    def __init__(
        self,
        gpio: object,
        rpwm_pin: int,
        lpwm_pin: int,
        r_en_pin: int,
        l_en_pin: int,
        pwm_frequency: float,
        name: str,
    ) -> None:
        """
        Инициализация драйвера BTS7960.

        Args:
            gpio: Модуль RPi.GPIO или его заглушка.
            rpwm_pin: Пин PWM для движения вперёд (BCM).
            lpwm_pin: Пин PWM для движения назад  (BCM).
            r_en_pin: Пин Enable правого чипа (BCM).
            l_en_pin: Пин Enable левого чипа  (BCM).
            pwm_frequency: Частота PWM в Гц (рекомендуется 10000-20000 для BTS7960).
            name: Имя мотора.
        """
        super().__init__(name)
        self._gpio = gpio
        self._r_en = r_en_pin
        self._l_en = l_en_pin

        # Настройка пинов Enable
        gpio.setup(r_en_pin, gpio.OUT)
        gpio.setup(l_en_pin, gpio.OUT)

        # Настройка PWM пинов
        gpio.setup(rpwm_pin, gpio.OUT)
        gpio.setup(lpwm_pin, gpio.OUT)

        # Активация Enable (оба чипа)
        gpio.output(r_en_pin, gpio.HIGH)
        gpio.output(l_en_pin, gpio.HIGH)

        # Инициализация PWM для обоих направлений
        self._rpwm = gpio.PWM(rpwm_pin, pwm_frequency)
        self._lpwm = gpio.PWM(lpwm_pin, pwm_frequency)
        self._rpwm.start(0)
        self._lpwm.start(0)

    def set_speed(self, speed_normalized: float) -> None:
        """
        Установить скорость BTS7960.

        Вперёд: RPWM = duty%, LPWM = 0
        Назад:  RPWM = 0, LPWM = duty%
        Стоп:   RPWM = 0, LPWM = 0

        Args:
            speed_normalized: Скорость от -1.0 до +1.0.
        """
        speed_normalized = max(-1.0, min(1.0, speed_normalized))
        self._current_speed = speed_normalized
        duty = abs(speed_normalized) * 100.0

        if speed_normalized > 0.01:
            # Движение вперёд
            self._rpwm.ChangeDutyCycle(duty)
            self._lpwm.ChangeDutyCycle(0)
        elif speed_normalized < -0.01:
            # Движение назад
            self._rpwm.ChangeDutyCycle(0)
            self._lpwm.ChangeDutyCycle(duty)
        else:
            # Стоп — оба PWM в ноль (плавный выбег)
            self._rpwm.ChangeDutyCycle(0)
            self._lpwm.ChangeDutyCycle(0)

    def stop(self) -> None:
        """Немедленная остановка: оба PWM в 0."""
        self._rpwm.ChangeDutyCycle(0)
        self._lpwm.ChangeDutyCycle(0)
        self._current_speed = 0.0

    def enable(self, active: bool = True) -> None:
        """
        Управление Enable пинами BTS7960.
        Позволяет полностью отключить чипы (например, при аварии).

        Args:
            active: True — Enable HIGH (активны), False — Enable LOW (отключены).
        """
        state = self._gpio.HIGH if active else self._gpio.LOW
        self._gpio.output(self._r_en, state)
        self._gpio.output(self._l_en, state)

    def cleanup(self) -> None:
        """Отключение Enable и остановка PWM."""
        self.stop()
        self.enable(False)  # Деактивируем чипы
        self._rpwm.stop()
        self._lpwm.stop()


# ---------------------------------------------------------------------------
# Конвертер Twist → дифференциальный привод
# ---------------------------------------------------------------------------

class DifferentialDriveConverter:
    """
    Конвертер Twist → скорости левого/правого моторов.

    Реализует микширование дифференциального привода:
        left_speed  = linear.x - angular.z
        right_speed = linear.x + angular.z
    """

    def __init__(
        self,
        max_linear_speed: float = 1.0,
        max_angular_speed: float = 1.0,
    ) -> None:
        self._max_linear = max_linear_speed
        self._max_angular = max_angular_speed

    def convert(self, twist: Twist) -> tuple[float, float]:
        """
        Конвертировать Twist в нормализованные скорости моторов.

        Returns:
            Кортеж (left_speed, right_speed) в диапазоне [-1.0, 1.0].
        """
        linear = twist.linear.x / self._max_linear if self._max_linear > 0 else 0.0
        angular = twist.angular.z / self._max_angular if self._max_angular > 0 else 0.0

        linear = max(-1.0, min(1.0, linear))
        angular = max(-1.0, min(1.0, angular))

        left = linear - angular
        right = linear + angular

        # Нормализация при выходе за [-1, 1]
        max_val = max(abs(left), abs(right), 1.0)
        left /= max_val
        right /= max_val

        return left, right


# ---------------------------------------------------------------------------
# ROS2 узел
# ---------------------------------------------------------------------------

class MotorControllerNode(Node):
    """
    ROS2 узел управления моторами для робота ControlCortase.

    Поддерживает два типа драйверов (параметр motor_driver_type):
      'l298n'   — L298N (ENA/IN1/IN2 + ENB/IN3/IN4)
      'bts7960' — BTS7960 (RPWM/LPWM/R_EN/L_EN × 2)

    Подписывается на /cmd_vel и управляет GPIO пинами выбранного драйвера.
    Watchdog 500 мс останавливает моторы при потере связи.
    Публикует диагностику на /diagnostics.
    """

    # Watchdog и диагностика
    WATCHDOG_TIMEOUT_MS = 500
    DIAGNOSTICS_PERIOD_S = 1.0

    # --- Пины L298N по умолчанию (BCM) ---
    DEFAULT_L298N = {
        'ena_pin': 25, 'in1_pin': 23, 'in2_pin': 24,
        'enb_pin': 18, 'in3_pin': 17, 'in4_pin': 27,
    }

    # --- Пины BTS7960 по умолчанию (BCM) ---
    # M1: RPWM=12, LPWM=13, R_EN=5, L_EN=6
    # M2: RPWM=19, LPWM=26, R_EN=20, L_EN=21
    DEFAULT_BTS7960 = {
        'm1_rpwm_pin': 12, 'm1_lpwm_pin': 13, 'm1_r_en_pin': 5,  'm1_l_en_pin': 6,
        'm2_rpwm_pin': 19, 'm2_lpwm_pin': 26, 'm2_r_en_pin': 20, 'm2_l_en_pin': 21,
    }

    # Частота PWM: L298N — 1 кГц достаточно, BTS7960 — рекомендуется 10-20 кГц
    DEFAULT_PWM_FREQ_L298N = 1000.0
    DEFAULT_PWM_FREQ_BTS7960 = 15000.0

    def __init__(self) -> None:
        super().__init__('motor_controller_node')

        self._declare_parameters()
        params = self._load_parameters()

        # Настройка GPIO
        self._gpio = GPIO if GPIO_AVAILABLE else MockGPIO
        if not GPIO_AVAILABLE:
            self.get_logger().warn(
                'RPi.GPIO недоступен! Используется Mock-режим. '
                'На Raspberry Pi установите: pip3 install RPi.GPIO'
            )

        self._driver_type: str = params['motor_driver_type'].lower()
        self._setup_gpio(params)

        # Конвертер Twist → дифф. привод
        self._converter = DifferentialDriveConverter(
            max_linear_speed=params['max_linear_speed'],
            max_angular_speed=params['max_angular_speed'],
        )

        # QoS — для управления важна актуальность, не надёжность
        cmd_vel_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Подписка на /cmd_vel
        self._cmd_vel_sub = self.create_subscription(
            Twist, '/cmd_vel', self._cmd_vel_callback, cmd_vel_qos,
        )

        # Watchdog таймер
        self._last_cmd_time: Optional[float] = None
        self._watchdog_timer = self.create_timer(
            self.WATCHDOG_TIMEOUT_MS / 1000.0,
            self._watchdog_callback,
        )

        # Диагностика
        self._diag_pub = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self._diag_timer = self.create_timer(self.DIAGNOSTICS_PERIOD_S, self._publish_diagnostics)

        self._motors_running = False

        self.get_logger().info(
            f'motor_controller_node запущен. '
            f'Драйвер: {self._driver_type.upper()}, '
            f'mock={not GPIO_AVAILABLE}'
        )

    def _declare_parameters(self) -> None:
        """Объявление всех ROS2 параметров узла."""
        # Тип драйвера
        self.declare_parameter('motor_driver_type', 'l298n')

        # Параметры L298N
        self.declare_parameter('ena_pin', self.DEFAULT_L298N['ena_pin'])
        self.declare_parameter('in1_pin', self.DEFAULT_L298N['in1_pin'])
        self.declare_parameter('in2_pin', self.DEFAULT_L298N['in2_pin'])
        self.declare_parameter('enb_pin', self.DEFAULT_L298N['enb_pin'])
        self.declare_parameter('in3_pin', self.DEFAULT_L298N['in3_pin'])
        self.declare_parameter('in4_pin', self.DEFAULT_L298N['in4_pin'])

        # Параметры BTS7960 — Мотор 1 (Левый)
        self.declare_parameter('m1_rpwm_pin', self.DEFAULT_BTS7960['m1_rpwm_pin'])
        self.declare_parameter('m1_lpwm_pin', self.DEFAULT_BTS7960['m1_lpwm_pin'])
        self.declare_parameter('m1_r_en_pin', self.DEFAULT_BTS7960['m1_r_en_pin'])
        self.declare_parameter('m1_l_en_pin', self.DEFAULT_BTS7960['m1_l_en_pin'])
        # Параметры BTS7960 — Мотор 2 (Правый)
        self.declare_parameter('m2_rpwm_pin', self.DEFAULT_BTS7960['m2_rpwm_pin'])
        self.declare_parameter('m2_lpwm_pin', self.DEFAULT_BTS7960['m2_lpwm_pin'])
        self.declare_parameter('m2_r_en_pin', self.DEFAULT_BTS7960['m2_r_en_pin'])
        self.declare_parameter('m2_l_en_pin', self.DEFAULT_BTS7960['m2_l_en_pin'])

        # Общие параметры
        self.declare_parameter('pwm_frequency', 0.0)  # 0 = авто (по типу драйвера)
        self.declare_parameter('max_linear_speed', 1.0)
        self.declare_parameter('max_angular_speed', 1.0)
        self.declare_parameter('watchdog_timeout_ms', self.WATCHDOG_TIMEOUT_MS)

    def _load_parameters(self) -> dict:
        """Загрузка параметров из ROS2 Parameter Server."""
        p = {
            'motor_driver_type': self.get_parameter('motor_driver_type').value,
            # L298N
            'ena_pin': self.get_parameter('ena_pin').value,
            'in1_pin': self.get_parameter('in1_pin').value,
            'in2_pin': self.get_parameter('in2_pin').value,
            'enb_pin': self.get_parameter('enb_pin').value,
            'in3_pin': self.get_parameter('in3_pin').value,
            'in4_pin': self.get_parameter('in4_pin').value,
            # BTS7960 M1
            'm1_rpwm_pin': self.get_parameter('m1_rpwm_pin').value,
            'm1_lpwm_pin': self.get_parameter('m1_lpwm_pin').value,
            'm1_r_en_pin': self.get_parameter('m1_r_en_pin').value,
            'm1_l_en_pin': self.get_parameter('m1_l_en_pin').value,
            # BTS7960 M2
            'm2_rpwm_pin': self.get_parameter('m2_rpwm_pin').value,
            'm2_lpwm_pin': self.get_parameter('m2_lpwm_pin').value,
            'm2_r_en_pin': self.get_parameter('m2_r_en_pin').value,
            'm2_l_en_pin': self.get_parameter('m2_l_en_pin').value,
            # Общие
            'pwm_frequency': self.get_parameter('pwm_frequency').value,
            'max_linear_speed': self.get_parameter('max_linear_speed').value,
            'max_angular_speed': self.get_parameter('max_angular_speed').value,
            'watchdog_timeout_ms': self.get_parameter('watchdog_timeout_ms').value,
        }
        return p

    def _resolve_pwm_frequency(self, params: dict) -> float:
        """Определить частоту PWM: из параметров или по умолчанию для типа драйвера."""
        freq = params['pwm_frequency']
        if freq <= 0.0:
            if params['motor_driver_type'].lower() == 'bts7960':
                freq = self.DEFAULT_PWM_FREQ_BTS7960
                self.get_logger().info(
                    f'PWM частота не задана — используется {freq:.0f} Гц '
                    f'(рекомендованная для BTS7960)'
                )
            else:
                freq = self.DEFAULT_PWM_FREQ_L298N
                self.get_logger().info(
                    f'PWM частота не задана — используется {freq:.0f} Гц '
                    f'(рекомендованная для L298N)'
                )
        return freq

    def _setup_gpio(self, params: dict) -> None:
        """Фабричный метод: инициализация GPIO и создание нужного драйвера."""
        self._gpio.setmode(self._gpio.BCM)
        self._gpio.setwarnings(False)

        freq = self._resolve_pwm_frequency(params)
        driver_type = params['motor_driver_type'].lower()

        if driver_type == 'bts7960':
            self._motor_left, self._motor_right = self._create_bts7960(params, freq)
        elif driver_type == 'l298n':
            self._motor_left, self._motor_right = self._create_l298n(params, freq)
        else:
            self.get_logger().error(
                f'Неизвестный тип драйвера: "{driver_type}". '
                f'Допустимо: l298n, bts7960. Используется l298n.'
            )
            self._motor_left, self._motor_right = self._create_l298n(params, freq)

    def _create_l298n(
        self, params: dict, freq: float
    ) -> tuple[L298NMotorDriver, L298NMotorDriver]:
        """Создать пару L298N драйверов."""
        self.get_logger().info(
            f'Инициализация L298N: '
            f'M1=[ENA={params["ena_pin"]}, IN1={params["in1_pin"]}, IN2={params["in2_pin"]}] '
            f'M2=[ENB={params["enb_pin"]}, IN3={params["in3_pin"]}, IN4={params["in4_pin"]}] '
            f'PWM={freq:.0f}Гц'
        )
        left = L298NMotorDriver(
            gpio=self._gpio,
            in1_pin=params['in1_pin'],
            in2_pin=params['in2_pin'],
            en_pin=params['ena_pin'],
            pwm_frequency=freq,
            name='M1_Left',
        )
        right = L298NMotorDriver(
            gpio=self._gpio,
            in1_pin=params['in3_pin'],
            in2_pin=params['in4_pin'],
            en_pin=params['enb_pin'],
            pwm_frequency=freq,
            name='M2_Right',
        )
        return left, right

    def _create_bts7960(
        self, params: dict, freq: float
    ) -> tuple[BTS7960MotorDriver, BTS7960MotorDriver]:
        """Создать пару BTS7960 драйверов."""
        self.get_logger().info(
            f'Инициализация BTS7960: '
            f'M1=[RPWM={params["m1_rpwm_pin"]}, LPWM={params["m1_lpwm_pin"]}, '
            f'R_EN={params["m1_r_en_pin"]}, L_EN={params["m1_l_en_pin"]}] '
            f'M2=[RPWM={params["m2_rpwm_pin"]}, LPWM={params["m2_lpwm_pin"]}, '
            f'R_EN={params["m2_r_en_pin"]}, L_EN={params["m2_l_en_pin"]}] '
            f'PWM={freq:.0f}Гц'
        )
        left = BTS7960MotorDriver(
            gpio=self._gpio,
            rpwm_pin=params['m1_rpwm_pin'],
            lpwm_pin=params['m1_lpwm_pin'],
            r_en_pin=params['m1_r_en_pin'],
            l_en_pin=params['m1_l_en_pin'],
            pwm_frequency=freq,
            name='M1_Left',
        )
        right = BTS7960MotorDriver(
            gpio=self._gpio,
            rpwm_pin=params['m2_rpwm_pin'],
            lpwm_pin=params['m2_lpwm_pin'],
            r_en_pin=params['m2_r_en_pin'],
            l_en_pin=params['m2_l_en_pin'],
            pwm_frequency=freq,
            name='M2_Right',
        )
        return left, right

    def _cmd_vel_callback(self, msg: Twist) -> None:
        """Обработчик сообщений /cmd_vel."""
        self._last_cmd_time = self.get_clock().now().nanoseconds

        try:
            left_speed, right_speed = self._converter.convert(msg)
            self._motor_left.set_speed(left_speed)
            self._motor_right.set_speed(right_speed)
            self._motors_running = (abs(left_speed) > 0.01 or abs(right_speed) > 0.01)

            self.get_logger().debug(
                f'cmd_vel → L={left_speed:.2f}, R={right_speed:.2f} '
                f'(lin={msg.linear.x:.2f}, ang={msg.angular.z:.2f})'
            )
        except Exception as e:
            self.get_logger().error(f'Ошибка обработки cmd_vel: {e}')
            self._emergency_stop()

    def _watchdog_callback(self) -> None:
        """
        Watchdog таймер — останавливает моторы при потере связи.
        Срабатывает если команды не поступали более watchdog_timeout_ms.
        """
        if self._last_cmd_time is None:
            return

        now_ns = self.get_clock().now().nanoseconds
        elapsed_ms = (now_ns - self._last_cmd_time) / 1_000_000
        timeout_ms = self.get_parameter('watchdog_timeout_ms').value

        if elapsed_ms > timeout_ms and self._motors_running:
            self.get_logger().warn(
                f'WATCHDOG: нет команд {elapsed_ms:.0f} мс > {timeout_ms} мс — СТОП!'
            )
            self._emergency_stop()

    def _emergency_stop(self) -> None:
        """Аварийная остановка всех моторов."""
        try:
            self._motor_left.stop()
            self._motor_right.stop()
            self._motors_running = False
        except Exception as e:
            self.get_logger().error(f'Ошибка аварийной остановки: {e}')

    def _publish_diagnostics(self) -> None:
        """Публикация диагностики в /diagnostics."""
        msg = DiagnosticArray()
        msg.header.stamp = self.get_clock().now().to_msg()

        status = DiagnosticStatus()
        status.name = 'motor_controller_node'
        status.hardware_id = 'controlcortase_pi'
        status.level = DiagnosticStatus.OK
        status.message = 'Моторы активны' if self._motors_running else 'Моторы в стопе'
        status.values = [
            KeyValue(key='driver_type', value=self._driver_type),
            KeyValue(key='gpio_available', value=str(GPIO_AVAILABLE)),
            KeyValue(key='left_speed', value=f'{self._motor_left.current_speed:.3f}'),
            KeyValue(key='right_speed', value=f'{self._motor_right.current_speed:.3f}'),
            KeyValue(key='motors_running', value=str(self._motors_running)),
        ]
        msg.status = [status]
        self._diag_pub.publish(msg)

    def destroy_node(self) -> None:
        """Корректное завершение работы узла с очисткой GPIO."""
        self.get_logger().info('Завершение motor_controller_node — остановка моторов...')
        self._emergency_stop()

        try:
            self._motor_left.cleanup()
            self._motor_right.cleanup()
        except Exception as e:
            self.get_logger().error(f'Ошибка cleanup моторов: {e}')

        try:
            self._gpio.cleanup()
        except Exception as e:
            self.get_logger().error(f'Ошибка GPIO cleanup: {e}')

        super().destroy_node()


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main(args=None) -> None:
    """Точка входа узла motor_controller_node."""
    rclpy.init(args=args)
    node = None

    try:
        node = MotorControllerNode()
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
