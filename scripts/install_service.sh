#!/bin/bash
# Install VoiceDesk as a systemd service (auto-start on boot)
set -e

SERVICE_FILE="/etc/systemd/system/voicedesk.service"
WORK_DIR="$(pwd)"
USER="$(whoami)"

echo "Installing VoiceDesk systemd service..."

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=VoiceDesk AI Server
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORK_DIR
ExecStart=$WORK_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable voicedesk
sudo systemctl start voicedesk

echo ""
echo "✓ Service installed and started"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status voicedesk    # check status"
echo "  sudo journalctl -u voicedesk -f    # live logs"
echo "  sudo systemctl restart voicedesk   # restart"
echo "  sudo systemctl stop voicedesk      # stop"
