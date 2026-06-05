#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  VoiceDesk Pi5 Server — One-time setup script
#  Run once after flashing OS and cloning the repo.
#  Usage: bash scripts/setup.sh
# ─────────────────────────────────────────────────────────────
set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   VoiceDesk Server Setup             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. System packages
echo "[1/7] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv python3-dev build-essential \
    cargo curl git avahi-daemon libavahi-compat-libdnssd-dev \
    ffmpeg pkg-config libavformat-dev libavcodec-dev libavdevice-dev \
    libavutil-dev libavfilter-dev libswscale-dev libswresample-dev

# 2. Enable mDNS (voicedesk.local)
echo "[2/7] Setting hostname to voicedesk..."
sudo hostnamectl set-hostname voicedesk
if ! grep -qE "^127\.0\.1\.1[[:space:]]+voicedesk" /etc/hosts; then
    echo "127.0.1.1 voicedesk" | sudo tee -a /etc/hosts >/dev/null
fi
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon

# 3. Install Ollama
echo "[3/7] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
fi
echo "  Pulling minimax-m3:cloud model (this may take a few minutes)..."
ollama pull minimax-m3:cloud

# 4. Install Piper TTS
echo "[4/7] Installing Piper TTS..."
USER_HOME="${SUDO_USER:+/home/$SUDO_USER}"
USER_HOME="${USER_HOME:-$HOME}"
PIPER_DIR="$USER_HOME/piper"
mkdir -p "$PIPER_DIR"
PIPER_URL="https://github.com/rhasspy/piper/releases/latest/download/piper_linux_aarch64.tar.gz"
curl -L "$PIPER_URL" | tar xz -C "$PIPER_DIR"
sudo ln -sf "$PIPER_DIR/piper" /usr/local/bin/piper
echo "  Downloading English voice model..."
VOICES_DIR="$USER_HOME/voicedesk/voices"
mkdir -p "$VOICES_DIR"
curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
     -o "$VOICES_DIR/en_US-lessac-medium.onnx"
curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
     -o "$VOICES_DIR/en_US-lessac-medium.onnx.json"

# 5. Python virtualenv + dependencies
echo "[5/7] Installing Python dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 6. Create .env from example
echo "[6/7] Creating .env config..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ✓ .env created — edit it to add your Google credentials path"
else
    echo "  .env already exists, skipping"
fi

# 7. Create directories
echo "[7/7] Creating runtime directories..."
mkdir -p audio_cache logs

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                     ║"
echo "║                                                      ║"
echo "║  Next steps:                                         ║"
echo "║  1. Add Google credentials.json to $USER_HOME/       ║"
echo "║     voicedesk/credentials.json                       ║"
echo "║  2. Edit .env if needed                              ║"
echo "║  3. Run: bash scripts/install_service.sh             ║"
echo "║     to install as systemd service                    ║"
echo "║  4. Or test directly: python main.py                 ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
