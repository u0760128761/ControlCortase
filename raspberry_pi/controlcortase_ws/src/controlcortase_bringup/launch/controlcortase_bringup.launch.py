#!/usr/bin/env python3
"""
Launch файл для запуска всех узлов системы ControlCortase.

Запускает:
  - motor_controller_node  (управление GPIO/PWM моторами)
  - bluetooth_bridge_node  (мост Bluetooth RFCOMM → /cmd_vel)

Использование:
    ros2 launch controlcortase_bringup controlcortase_bringup.launch.py
    ros2 launch controlcortase_bringup controlcortase_bringup.launch.py params_file:=/path/to/custom_params.yaml
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.conditions import IfCondition
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Генерация объекта LaunchDescription для запуска системы."""

    # Путь к директории пакета bringup
    bringup_dir = get_package_share_directory('controlcortase_bringup')

    # Путь к файлу параметров по умолчанию
    default_params_file = os.path.join(bringup_dir, 'config', 'params.yaml')

    # Аргумент для переопределения файла параметров
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params_file,
        description='Путь к YAML файлу параметров (переопределяет значения по умолчанию)',
    )

    # Аргумент для отключения Bluetooth моста (например, при тестировании)
    use_bluetooth_arg = DeclareLaunchArgument(
        'use_bluetooth',
        default_value='true',
        description='Запускать ли Bluetooth Bridge узел',
    )

    params_file = LaunchConfiguration('params_file')
    use_bluetooth = LaunchConfiguration('use_bluetooth')

    # Узел управления моторами
    motor_controller_node = Node(
        package='controlcortase_motor',
        executable='motor_controller_node',
        name='motor_controller_node',
        namespace='controlcortase',
        parameters=[params_file],
        output='screen',
        emulate_tty=True,
        remappings=[
            # Позволяет переключиться на другой topik без изменения кода
            ('/cmd_vel', '/cmd_vel'),
        ],
    )

    # Узел Bluetooth моста
    bluetooth_bridge_node = Node(
        package='controlcortase_bluetooth_bridge',
        executable='bluetooth_bridge_node',
        name='bluetooth_bridge_node',
        namespace='controlcortase',
        parameters=[params_file],
        output='screen',
        emulate_tty=True,
        condition=IfCondition(use_bluetooth),
    )

    return LaunchDescription([
        params_file_arg,
        use_bluetooth_arg,
        LogInfo(msg='--- Запуск системы ControlCortase (ROS2 Humble) ---'),
        motor_controller_node,
        bluetooth_bridge_node,
    ])
