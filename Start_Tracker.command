#!/bin/bash

# Move into the folder where this script lives
cd "$(dirname "$0")"

# Check if the virtual environment exists. If not, build it.
if [ ! -d "venv" ]; then
    echo "First time setup: Building environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    # If it already exists, just activate it
    source venv/bin/activate
fi

# Run the app
echo "Booting up the GoWise Job Tracker..."
python app.py