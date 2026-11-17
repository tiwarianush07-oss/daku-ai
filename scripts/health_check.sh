#!/usr/bin/env bash
# ==============================================================================
# DAKU + HERMES — SERVER HEALTH & STATUS DIAGNOSTIC SCRIPT
# ==============================================================================

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}                 DAKU SERVER HEALTH MONITOR                   ${NC}"
echo -e "${BLUE}==============================================================${NC}"

# 1. Check Systemd Units
echo -e "\n[1] Systemd Service Units:"
for SVC in daku hermes nginx; do
    if systemctl is-active --quiet "${SVC}" 2>/dev/null; then
        echo -e "    ${SVC}.service : ${GREEN}ACTIVE (Running)${NC}"
    else
        echo -e "    ${SVC}.service : ${YELLOW}INACTIVE / STOPPED${NC}"
    fi
done

# 2. Query Internal DAKU Backend (127.0.0.1:8443)
echo -e "\n[2] Internal DAKU Daemon (127.0.0.1:8443):"
if curl -s -f http://127.0.0.1:8443/health >/tmp/daku_health.json 2>/dev/null; then
    echo -e "    Internal /health : ${GREEN}ONLINE (HTTP 200)${NC}"
    VERSION=$(grep -o '"version": "[^"]*' /tmp/daku_health.json | cut -d'"' -f4 || echo "unknown")
    UPTIME=$(grep -o '"uptime_seconds": [0-9.]*' /tmp/daku_health.json | cut -d' ' -f2 || echo "0")
    MODEL=$(grep -o '"model_name": "[^"]*' /tmp/daku_health.json | cut -d'"' -f4 || echo "unknown")
    HERMES=$(grep -o '"hermes": "[^"]*' /tmp/daku_health.json | cut -d'"' -f4 || echo "unknown")
    echo "    Version          : ${VERSION}"
    echo "    Uptime           : ${UPTIME} seconds"
    echo "    Model            : ${MODEL}"
    echo "    Hermes Gateway   : ${HERMES}"
    rm -f /tmp/daku_health.json
else
    echo -e "    Internal /health : ${RED}OFFLINE (Connection Refused)${NC}"
fi

# 3. Query Public HTTPS Reverse Proxy (Port 443 TLS)
echo -e "\n[3] HTTPS Reverse Proxy & TLS Termination (Port 443):"
if curl -k -s -f https://127.0.0.1/health >/dev/null 2>&1; then
    echo -e "    HTTPS /health    : ${GREEN}ONLINE (Port 443 TLS Terminated)${NC}"
    if [[ -f /etc/ssl/daku/server.crt ]]; then
        CERT_EXP=$(openssl x509 -enddate -noout -in /etc/ssl/daku/server.crt 2>/dev/null | cut -d= -f2 || echo "N/A")
        CERT_SUBJ=$(openssl x509 -subject -noout -in /etc/ssl/daku/server.crt 2>/dev/null | cut -d= -f2 || echo "N/A")
        echo "    TLS Certificate  : Valid (Subject: ${CERT_SUBJ}, Expires: ${CERT_EXP})"
    fi
else
    echo -e "    HTTPS /health    : ${YELLOW}NOT REACHABLE VIA LOCAL PORT 443 (Check Nginx / SSL)${NC}"
fi

# 4. System Resources
echo -e "\n[4] Host Resources:"
RAM_FREE=$(free -m | awk '/Mem:/ {print $4}')
RAM_TOTAL=$(free -m | awk '/Mem:/ {print $2}')
DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
echo "    RAM Free         : ${RAM_FREE} MB / ${RAM_TOTAL} MB"
echo "    Disk Available   : ${DISK_FREE}"
echo -e "\n${BLUE}==============================================================${NC}"
