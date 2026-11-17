#!/usr/bin/env bash
# ==============================================================================
# DAKU + HERMES — IDEMPOTENT REMOTE SERVER INSTALLER
# Target OS: Ubuntu 22.04 / 24.04 LTS (Oracle Cloud Always Free - ARM64 / x86)
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}   DAKU + HERMES REMOTE SERVER INSTALLER (Always Free Tier)   ${NC}"
echo -e "${BLUE}==============================================================${NC}"

# 1. Root check
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}[ERROR] This script must be run as root (e.g. sudo bash install_server.sh)${NC}" 
   exit 1
fi

# 2. Architecture & OS Detection
ARCH=$(uname -m)
OS_ID=$(grep -E '^ID=' /etc/os-release | cut -d= -f2 | tr -d '"')
echo -e "${GREEN}[1/8] Checking Hardware & OS...${NC}"
echo "      Architecture: ${ARCH}"
echo "      Distribution: ${OS_ID}"

if [[ "${OS_ID}" != "ubuntu" && "${OS_ID}" != "debian" ]]; then
    echo -e "${YELLOW}[WARN] Target distribution is recommended to be Ubuntu or Debian.${NC}"
fi

# 3. Install System Dependencies
echo -e "${GREEN}[2/9] Installing minimal system prerequisites & Nginx...${NC}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    git \
    ufw \
    ca-certificates \
    ripgrep \
    tar \
    nginx \
    openssl \
    certbot \
    python3-certbot-nginx

# 4. Create unprivileged system user
echo -e "${GREEN}[3/9] Setting up unprivileged system user 'daku'...${NC}"
if ! id "daku" &>/dev/null; then
    useradd -m -s /bin/bash daku
    echo "      User 'daku' created."
else
    echo "      User 'daku' already exists."
fi

# 5. Install uv & Hermes Agent
echo -e "${GREEN}[4/9] Installing uv and Hermes Agent for 'daku' user...${NC}"
su - daku -c '
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "Installing uv package manager..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    if ! command -v hermes &>/dev/null; then
        echo "Installing Hermes Agent..."
        curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash || true
    fi
'

# 6. Setup DAKU directory structure & permissions
echo -e "${GREEN}[5/9] Configuring /opt/daku and /etc/daku...${NC}"
mkdir -p /opt/daku
mkdir -p /etc/daku
mkdir -p /var/log/daku

# Copy files from current directory if installing from repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

if [[ -f "${REPO_DIR}/main.py" && -d "${REPO_DIR}/brain" ]]; then
    echo "      Syncing DAKU codebase into /opt/daku..."
    cp -r "${REPO_DIR}"/* /opt/daku/
fi

# Setup Python Virtual Environment
if [[ ! -d /opt/daku/venv ]]; then
    echo "      Creating Python virtual environment in /opt/daku/venv..."
    python3 -m venv /opt/daku/venv
fi

# Install requirements if present
if [[ -f /opt/daku/requirements.txt ]]; then
    /opt/daku/venv/bin/pip install --upgrade pip --quiet
    /opt/daku/venv/bin/pip install -r /opt/daku/requirements.txt --quiet || true
fi

# Setup Environment File
ENV_FILE="/etc/daku/daku.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "      Generating secure configuration in ${ENV_FILE}..."
    AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    cat <<EOF > "$ENV_FILE"
# DAKU Remote Server Configuration
DAKU_MODE=cloud-server
LOG_LEVEL=INFO
# Behind Nginx TLS reverse proxy, DAKU binds to loopback
DAKU_SERVER_HOST=127.0.0.1
DAKU_SERVER_PORT=8443
DAKU_AUTH_TOKEN=${AUTH_TOKEN}
HERMES_GATEWAY_URL=http://127.0.0.1:8080

# Cloud LLM Model Configuration (Hosted API)
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-chat
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=your_api_key_here
MODEL_TIMEOUT_SECONDS=15.0

# Safety
REQUIRE_CONFIRMATION=true
EOF
    chmod 600 "$ENV_FILE"
    chown daku:daku "$ENV_FILE"
fi

# Fix ownership
chown -R daku:daku /opt/daku
chown -R daku:daku /var/log/daku

# 7. Configure Nginx TLS Reverse Proxy
echo -e "${GREEN}[6/9] Configuring Nginx TLS Reverse Proxy (Port 443)...${NC}"
mkdir -p /etc/ssl/daku
if [[ ! -f /etc/ssl/daku/server.crt || ! -f /etc/ssl/daku/server.key ]]; then
    echo "      Generating initial high-entropy 2048-bit RSA TLS certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/daku/server.key \
        -out /etc/ssl/daku/server.crt \
        -subj "/C=IN/ST=DAKU/L=Cloud/O=DAKU/OU=Agent/CN=daku-server" \
        2>/dev/null
    chmod 600 /etc/ssl/daku/server.key
    chmod 644 /etc/ssl/daku/server.crt
fi

cat <<'EOF' > /etc/nginx/sites-available/daku
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name _;

    ssl_certificate /etc/ssl/daku/server.crt;
    ssl_certificate_key /etc/ssl/daku/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 2M;

    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/daku /etc/nginx/sites-enabled/daku
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

# 8. Configure Systemd Services
echo -e "${GREEN}[7/9] Installing and enabling systemd units...${NC}"
if [[ -f /opt/daku/systemd/daku.service ]]; then
    cp /opt/daku/systemd/daku.service /etc/systemd/system/daku.service
fi
if [[ -f /opt/daku/systemd/hermes.service ]]; then
    cp /opt/daku/systemd/hermes.service /etc/systemd/system/hermes.service
fi

systemctl daemon-reload
systemctl enable daku.service || true
systemctl enable hermes.service || true

# 9. Configure UFW Firewall (Least-Open Ports: 22, 80, 443)
echo -e "${GREEN}[8/9] Hardening firewall (UFW: 22 SSH, 80 HTTP, 443 HTTPS)...${NC}"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH Key Access'
ufw allow 80/tcp comment 'HTTP Redirect / ACME'
ufw allow 443/tcp comment 'DAKU HTTPS API'
# Close direct external 8443; all traffic now routes through port 443 TLS
ufw delete allow 8443/tcp 2>/dev/null || true
ufw --force enable

# 10. Start / Restart Services
echo -e "${GREEN}[9/9] Starting DAKU services...${NC}"
systemctl restart daku.service || true

echo -e "\n${GREEN}==============================================================${NC}"
echo -e "${GREEN}             DAKU SERVER INSTALLATION COMPLETE!               ${NC}"
echo -e "${GREEN}==============================================================${NC}"

PUBLIC_IP=$(curl -s -4 https://ifconfig.me || hostname -I | awk '{print $1}')
AUTH_TOKEN_DISPLAY=$(grep -E '^DAKU_AUTH_TOKEN=' /etc/daku/daku.env | cut -d= -f2)

echo -e "Server Status:"
echo -e "  Public IP    : ${PUBLIC_IP}"
echo -e "  HTTPS Port   : 443 (Nginx Reverse Proxy + TLS)"
echo -e "  DAKU Port    : 127.0.0.1:8443 (Internal)"
echo -e "  Auth Token   : ${AUTH_TOKEN_DISPLAY}"
echo -e "\nNext Steps for your Windows 11 Laptop:"
echo -e "  1. Open your laptop's .env file in the DAKU folder"
echo -e "  2. Set:"
echo -e "     DAKU_SERVER_URL=https://${PUBLIC_IP}"
echo -e "     DAKU_AUTH_TOKEN=${AUTH_TOKEN_DISPLAY}"
echo -e "  3. Run on your laptop:"
echo -e "     py doctor.py --remote"
echo -e "     py client.py"
echo -e "\nFor Public Domain & Let's Encrypt Certificate:"
echo -e "  If you have a domain (e.g. daku.yourdomain.com pointing to ${PUBLIC_IP}):"
echo -e "  sudo certbot --nginx -d daku.yourdomain.com"
echo -e "=============================================================="
