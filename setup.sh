#!/bin/bash
# Setup script for MATE 2026 ROV system
# Run this on both LattePanda and Laptop to install dependencies and build workspace

set -e  # Exit on error

echo "============================================"
echo "MATE 2026 ROV - Automated Setup Script"
echo "============================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if ROS 2 is installed
if ! command -v ros2 &> /dev/null; then
    echo -e "${RED}✗ ROS 2 not found${NC}"
    echo "Please install ROS 2 Humble from: https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi

echo -e "${GREEN}✓ ROS 2 detected${NC}"
source /opt/ros/humble/setup.bash

# Determine system type
if grep -q "LattePanda" /etc/hostname 2>/dev/null || grep -q "lattepanda" /etc/hostname 2>/dev/null; then
    echo "Detected: LattePanda (onboard computer)"
    IS_ONBOARD=true
else
    echo "Detected: Control Station (laptop/Jetson)"
    IS_ONBOARD=false
fi

echo ""
echo "Installing system dependencies..."

# Update system
sudo apt update -y

# Common packages for both systems
sudo apt install -y \
    build-essential \
    git \
    python3-pip \
    python3-dev \
    python3-opencv \
    python3-yaml \
    ros-humble-cv-bridge \
    ros-humble-image-transport

# Install MAVROS only on LattePanda
if [ "$IS_ONBOARD" = true ]; then
    echo "Installing MAVROS2..."
    sudo apt install -y ros-humble-mavros ros-humble-mavros-msgs

    # Install GeographicLib datasets
    echo "Installing GeographicLib datasets..."
    cd ~/
    wget -q https://raw.githubusercontent.com/mavlink/mavros/humble-devel/mavros/scripts/install_geographiclib_datasets.sh
    chmod +x install_geographiclib_datasets.sh
    sudo ./install_geographiclib_datasets.sh
    rm install_geographiclib_datasets.sh
fi

# Install pygame for gamepad support
echo "Installing pygame..."
pip3 install --upgrade pip setuptools wheel
pip3 install pygame pyyaml

echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Setup ROS 2 domain ID
echo "Setting ROS 2 Domain ID..."
if ! grep -q "ROS_DOMAIN_ID" ~/.bashrc; then
    echo 'export ROS_DOMAIN_ID=42' >> ~/.bashrc
    echo -e "${GREEN}✓ Added ROS_DOMAIN_ID=42 to ~/.bashrc${NC}"
else
    echo -e "${YELLOW}! ROS_DOMAIN_ID already in ~/.bashrc${NC}"
fi

# Workspace setup
WORKSPACE_PATH=~/mate_rov_ws

if [ ! -d "$WORKSPACE_PATH" ]; then
    echo -e "${RED}✗ Workspace not found at $WORKSPACE_PATH${NC}"
    echo "Please ensure workspace is at ~/mate_rov_ws"
    exit 1
fi

echo ""
echo "Building workspace at $WORKSPACE_PATH..."
cd "$WORKSPACE_PATH"

# Source ROS 2
source /opt/ros/humble/setup.bash

# Build with colcon
if ! colcon build --symlink-install; then
    echo -e "${RED}✗ Build failed${NC}"
    echo "Try running: rosdep install --from-paths src --ignore-src -r -y"
    exit 1
fi

echo -e "${GREEN}✓ Workspace built successfully${NC}"

# Add workspace sourcing to bashrc
if ! grep -q "mate_rov_ws/install/setup.bash" ~/.bashrc; then
    echo "source $WORKSPACE_PATH/install/setup.bash" >> ~/.bashrc
    echo -e "${GREEN}✓ Added workspace to ~/.bashrc${NC}"
else
    echo -e "${YELLOW}! Workspace already in ~/.bashrc${NC}"
fi

echo ""
echo "============================================"
echo -e "${GREEN}Setup Complete!${NC}"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Reload your shell: source ~/.bashrc"
echo "2. If on LattePanda: Connect PIX6 via USB and verify with 'ls /dev/ttyACM*'"
echo "3. Check INSTALLATION_GUIDE.md for next steps"
echo ""
echo "To launch:"
if [ "$IS_ONBOARD" = true ]; then
    echo "  On LattePanda: ros2 launch rov_onboard onboard_launch.py"
else
    echo "  On Laptop: ros2 launch rov_control control_launch.py"
fi

