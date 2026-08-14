from glob import glob

from setuptools import find_packages, setup

PACKAGE_NAME = "iscps_sst_lab"

setup(
    name=PACKAGE_NAME,
    version="2.0.0",
    packages=find_packages(exclude=["test", "test.*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE_NAME}"]),
        (f"share/{PACKAGE_NAME}", ["package.xml"]),
        (f"share/{PACKAGE_NAME}/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools", "Pillow", "pydantic>=2", "PyYAML"],
    zip_safe=True,
    maintainer="Hokeun Kim",
    maintainer_email="hokeun@asu.edu",
    description=(
        "ISCPS course project: securing multimodal perception for a ROS 2 VLM "
        "agent with the Secure Swarm Toolkit."
    ),
    license="BSD-2-Clause",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            f"distance_sensor_node = {PACKAGE_NAME}.distance_sensor_node:main",
            f"vision_node = {PACKAGE_NAME}.vision_node:main",
            f"vlm_agent_node = {PACKAGE_NAME}.vlm_agent_node:main",
            f"cart_simulator_node = {PACKAGE_NAME}.cart_simulator_node:main",
            (
                "malicious_distance_sensor_node = "
                f"{PACKAGE_NAME}.malicious_distance_sensor_node:main"
            ),
            f"malicious_vision_node = {PACKAGE_NAME}.malicious_vision_node:main",
        ],
    },
)
