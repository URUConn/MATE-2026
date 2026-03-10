#!/bin/bash
# MATE-2026 ROV - Quick Installation Script
# Run this on a fresh Ubuntu 22.04 installation

set -e  # Exit on error

echo "=========================================="
echo "MATE-2026 ROV - Quick Setup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Ubuntu 22.04
if ! grep -q "jammy\|22.04" /etc/os-release; then
    echo -e "${YELLOW}Warning: This script is optimized for Ubuntu 22.04${NC}"
fi

# Step 1: Update system
echo -e "\n${GREEN}[1/8] Updating system packages...${NC}"
sudo apt update
sudo apt upgrade -y

# Step 2: Install ROS2 Humble
echo -e "\n${GREEN}[2/8] Installing ROS2 Humble...${NC}"
if ! command -v ros2 &> /dev/null; then
    sudo apt install -y software-properties-common curl gnupg lsb-release
    sudo add-apt-repository universe -y
    curl -sSL https://repo.ros2.org/ros.key | sudo apt-key add -
    sudo sh -c 'echo "deb [arch=$(dpkg --print-architecture)] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ros2-latest.list'
    sudo apt update
    sudo apt install -y ros-humble-desktop ros-humble-launch ros-humble-launch-ros
    echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
    source /opt/ros/humble/setup.bash
    echo -e "${GREEN}ROS2 Humble installed${NC}"
else
    echo -e "${YELLOW}ROS2 already installed${NC}"
fi

# Step 3: Install build tools
echo -e "\n${GREEN}[3/8] Installing build tools...${NC}"
sudo apt install -y python3-colcon-common-extensions python3-rosdep python3-pip git

# Step 4: Create workspace
echo -e "\n${GREEN}[4/8] Creating ROS2 workspace...${NC}"
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws

# Step 5: Install Python dependencies
echo -e "\n${GREEN}[5/8] Installing Python dependencies...${NC}"
pip install pymavlink dronekit pyserial

# Step 6: Install system dependencies
echo -e "\n${GREEN}[6/8] Installing system dependencies...${NC}"
sudo apt install -y libopencv-dev python3-opencv v4l-utils

# Step 7: Clone or copy repository
echo -e "\n${GREEN}[7/8] Setting up MATE-2026 repository...${NC}"
if [ ! -d "src/rov_msgs" ]; then
    echo "Please ensure MATE-2026 repository is in ~/mate_rov_ws/src"
    echo "You can clone it with: git clone <repo-url> ~/mate_rov_ws/src/"
    exit 1
fi

# Install ROS dependencies
rosdep update
rosdep install --from-paths src --ignore-src -r -y

# Step 8: Build workspace
echo -e "\n${GREEN}[8/8] Building workspace...${NC}"
colcon build --symlink-install

# Final steps
echo -e "\n${GREEN}=========================================="
echo "Installation Complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Source the setup script:"
echo "   source ~/mate_rov_ws/install/setup.bash"
echo ""
echo "2. Configure MAVLink connection in:"
echo "   ~/mate_rov_ws/src/rov_mavlink/config/mavlink_params.yaml"
echo ""
echo "3. Read the setup guide:"
echo "   ~/mate_rov_ws/src/MAVLINK_SETUP.md"
echo ""
echo "4. On LattePanda, launch the system:"
echo "   ros2 launch rov_onboard onboard_launch.py"
echo ""
echo "5. On Control Laptop, launch control:"
echo "   ros2 launch rov_control control_launch.py"
echo ""
echo "For detailed instructions, see MAVLINK_SETUP.md"

