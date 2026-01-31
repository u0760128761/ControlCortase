#!/bin/bash
set -e

APP_NAME="controlcortase"
REPO_DIR="/opt/ControlCortase"
SRC_DIR="$REPO_DIR/raspberry_pi"
APP_DIR="/opt/controlcortase_app"
SERVICE_NAME="controlcortase.service"

echo "=== Deploy started: $(date) ==="

cd "$REPO_DIR"

echo "Pull latest code..."
git pull

echo "Ensure deploy.sh is executable..."
sudo chmod +x "$SRC_DIR/deploy.sh"

echo "Stopping service..."
sudo systemctl stop "$SERVICE_NAME" || true

echo "Creating app directory..."
sudo mkdir -p "$APP_DIR"
sudo chown creador:creador "$APP_DIR"

echo "Sync files..."
rsync -av --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  "$SRC_DIR/" "$APP_DIR/"

if [ -f "$APP_DIR/requirements.txt" ]; then
  echo "Installing Python dependencies..."
  # Force install with sudo to ensure they are available for the root service
  sudo pip3 install -r "$APP_DIR/requirements.txt" --break-system-packages
else
  echo "Warning: requirements.txt not found. Installing defaults..."
  # Install via apt for system stability and pip for the app
  sudo apt-get install -y python3-gpiozero
  sudo pip3 install flask gpiozero --break-system-packages
fi

echo "Fix permissions..."
chmod +x "$APP_DIR"/*.sh 2>/dev/null || true

echo "Starting service..."
sudo systemctl start "$SERVICE_NAME"

echo "Deploy finished successfully"
