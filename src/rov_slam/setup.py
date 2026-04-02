from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'rov_slam'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
        (os.path.join('share', package_name, 'rviz'),
            glob(os.path.join('rviz', '*.rviz'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='URUC',
    maintainer_email='URUC.UCONN@gmail.com',
    description='Control-side monocular SLAM and visualization pipeline for the MATE ROV',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_calibration_node = rov_slam.camera_calibration_node:main',
            'generate_checkerboard = rov_slam.checkerboard_generator:main',
            'monocular_slam_node = rov_slam.monocular_slam_node:main',
        ],
    },
)

