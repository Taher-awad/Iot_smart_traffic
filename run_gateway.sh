#!/bin/bash
# Helper script to run traffic_gateway.py using the virtual environment

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install paho-mqtt AWSIoTPythonSDK
fi

echo "Starting Traffic Gateway..."
./venv/bin/python traffic_gateway.py
