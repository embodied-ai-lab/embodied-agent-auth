from setuptools import setup

PACKAGE_NAME = "lab"

setup(
    name=PACKAGE_NAME,
    version="2.0.0",
    packages=[PACKAGE_NAME],
    # The ROS project directory is also the import package. Use a normal
    # (non-editable) colcon build so setuptools installs it as ``lab``.
    package_dir={PACKAGE_NAME: "."},
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE_NAME}"]),
        (f"share/{PACKAGE_NAME}", ["package.xml"]),
        (f"share/{PACKAGE_NAME}/launch", ["launch/lab.launch.py"]),
    ],
    install_requires=["setuptools", "Pillow", "pydantic>=2", "PyYAML"],
    zip_safe=True,
    maintainer="CSE 494/598 Course Staff",
    maintainer_email="iscps-lab@example.invalid",
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
            f"vlm_agent_node = {PACKAGE_NAME}.vlm:main",
            f"cart_simulator_node = {PACKAGE_NAME}.cart_simulator_node:main",
            (
                "malicious_distance_sensor_node = "
                f"{PACKAGE_NAME}.malicious_distance_sensor_node:main"
            ),
            f"malicious_vision_node = {PACKAGE_NAME}.malicious_vision_node:main",
        ],
    },
)
