#!/bin/bash

# Exit on error
set -e

echo "--- Initializing Local Environment ---"

# 1. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv/..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

# 2. Activate the environment
echo "Activating environment..."
source .venv/bin/activate

# 3. Install/Update dependencies
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

echo "--------------------------------------"
echo "SETUP COMPLETE"
echo "To start the manager, run:"
echo "  source .venv/bin/activate"
echo "  python gmail_scanner.py"
echo "--------------------------------------"
