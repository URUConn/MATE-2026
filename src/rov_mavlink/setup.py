from setuptools import find_packages, setup

)
    },
        ],
            'mavlink_bridge_node = rov_mavlink.mavlink_bridge_node:main',
        'console_scripts': [
    entry_points={
    tests_require=['pytest'],
    license='MIT',
    description='MAVLink bridge for MATE ROV (ArduSub/PIX6 communication)',
    maintainer_email='team@mate-rov.org',
    maintainer='MATE ROV Team',
    zip_safe=True,
    install_requires=['setuptools', 'pymavlink'],
    ],
            glob(os.path.join('config', '*.yaml'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'launch'),
        ('share/' + package_name, ['package.xml']),
            ['resource/' + package_name]),
        ('share/ament_index/resource_index/packages',
    data_files=[
    packages=find_packages(exclude=['test']),
    version='0.1.0',
    name=package_name,
setup(

package_name = 'rov_mavlink'

from glob import glob
import os
