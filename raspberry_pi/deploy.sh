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
  pip3 install -r "$APP_DIR/requirements.txt"
fi

echo "Fix permissions..."
chmod +x "$APP_DIR"/*.sh 2>/dev/null || true

echo "Starting service..."
sudo systemctl start "$SERVICE_NAME"

echo "Deploy finished successfully"
