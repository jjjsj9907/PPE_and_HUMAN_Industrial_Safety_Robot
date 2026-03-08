from setuptools import find_packages, setup

package_name = 'rokey_pjt'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jsj2204',
    maintainer_email='jsj2204@todo.todo',
    description='TODO: Package description',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'tf_point_node = rokey_pjt.tf_point_node:main',
            'bounding_node = rokey_pjt.bounding_node:main',
            'depth_node_center = rokey_pjt.depth_node_center_calcul:main',
            "detect_with_depth_with_tf = rokey_pjt.detect_with_depth_with_tf:main"
        ],
    },
)
