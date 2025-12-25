#!/bin/bash
# Simple Python HTTP Server to avoid CORS issues
cd "$(dirname "$0")/web"
echo "Starting Web Server at http://localhost:8000"
echo "Press Ctrl+C to stop"
python3 -m http.server 8000
