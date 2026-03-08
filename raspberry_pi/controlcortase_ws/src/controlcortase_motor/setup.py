from setuptools import setup

package_name = 'controlcortase_motor'

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
    description='ROS2 motor controller node for ControlCortase differential drive robot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motor_controller_node = controlcortase_motor.motor_controller_node:main',
        ],
    },
)
