from setuptools import setup
import os
from glob import glob

package_name = 'controlcortase_bringup'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Установка launch файлов
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        # Установка конфигурационных файлов
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ControlCortase Project',
    maintainer_email='admin@controlcortase.local',
    description='Bringup launch files and configuration for ControlCortase robot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [],
    },
)
