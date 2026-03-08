from setuptools import setup

package_name = 'controlcortase_bluetooth_bridge'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ControlCortase Project',
    maintainer_email='admin@controlcortase.local',
    description='ROS2 Bluetooth RFCOMM bridge for ControlCortase robot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'bluetooth_bridge_node = controlcortase_bluetooth_bridge.bluetooth_bridge_node:main',
        ],
    },
)
