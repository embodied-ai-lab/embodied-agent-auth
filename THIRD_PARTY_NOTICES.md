# Third-party notices

## Secure Swarm Toolkit / IoTAuth

The pinned source is the Git submodule at `third_party/iotauth`, licensed under
BSD-2-Clause. The lab installs its Python entity API from
`third_party/iotauth/entity/python` and builds Auth from the submodule.
Generated runtime material is not part of the submodule.

Project: <https://github.com/iotauth/iotauth>

## ROS 2

The lab targets ROS 2 Jazzy and uses `rclpy`, `sensor_msgs`, `std_msgs`, launch,
and launch_ros. ROS 2 packages retain their upstream licenses.

Documentation: <https://docs.ros.org/en/jazzy/>

## Ollama and qwen2.5vl

The live model is served by a separately installed Ollama endpoint. No model
weights are distributed with this repository.

- Ollama: <https://ollama.com/>
- qwen2.5vl:3b: <https://ollama.com/library/qwen2.5vl:3b>

## Python packages

Pydantic, Pillow, PyYAML, pytest, and Ruff are installed by `make setup` and
retain their upstream licenses.
