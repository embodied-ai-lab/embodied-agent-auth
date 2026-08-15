# syntax=docker/dockerfile:1
FROM ros:jazzy

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions \
        python3-pip \
        python3-venv \
        openjdk-17-jdk-headless \
        maven \
        openssl \
        nodejs \
        npm \
        git \
        make \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/embodied-agent-auth
COPY . .

# The build context must contain the initialized third_party/iotauth submodule.
# This installs from that source directly; it does not generate credentials.
RUN ./scripts/setup.sh
RUN ./scripts/build.sh

ENV ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /etc/bash.bashrc \
    && echo '[ -f /opt/embodied-agent-auth/ros2_ws/install/setup.bash ] && source /opt/embodied-agent-auth/ros2_ws/install/setup.bash' >> /etc/bash.bashrc

CMD ["/bin/bash"]
