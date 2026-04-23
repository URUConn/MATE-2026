from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'rov_control'

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
    ],
    install_requires=['setuptools', 'pyserial'],
    zip_safe=True,
    maintainer='URUC',
    maintainer_email='URUC.UCONN@gmail.com',
    description='Control station nodes for MATE ROV (runs on laptop)',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'arm_encoder_bridge_node = rov_control.arm_encoder_bridge_node:main',
            'qgc_video_bridge_node = rov_control.qgc_video_bridge_node:main',
            'crab_trigger_node = rov_control.crab_trigger_node:main',
        ],
    },
)
