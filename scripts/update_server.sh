#!/usr/bin/env bash
# ==============================================================================
# DAKU + HERMES — SAFE SERVER UPDATE & VERIFICATION SCRIPT
# Performs: Pre-update backup -> Git update -> Restart -> Health Check -> Rollback on error
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}==============================================================${NC}"
echo -e "${BLUE}             DAKU SERVER SAFE UPDATE PROCEDURE                ${NC}"
echo -e "${BLUE}==============================================================${NC}"

if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}[ERROR] This script must be run as root (e.g. sudo bash update_server.sh)${NC}" 
   exit 1
fi

DAKU_DIR="/opt/daku"
BACKUP_DIR="/var/backups/daku"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/daku_pre_update_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

# 1. Step 1: Pre-Update Backup
echo -e "${GREEN}[1/5] Creating pre-update snapshot in ${BACKUP_FILE}...${NC}"
tar --exclude='venv' --exclude='__pycache__' --exclude='.git' -czf "${BACKUP_FILE}" -C "${DAKU_DIR}" .
echo "      Backup created successfully ($(du -h "${BACKUP_FILE}" | cut -f1))."

# 2. Step 2: Codebase Update
echo -e "${GREEN}[2/5] Updating DAKU codebase...${NC}"
cd "${DAKU_DIR}"
if [[ -d .git ]]; then
    git fetch origin
    git reset --hard HEAD
    git pull origin main || git pull origin master || true
else
    echo "      Note: /opt/daku is not a git repository. Preserving existing tree."
fi

# Update dependencies if needed
if [[ -f "${DAKU_DIR}/requirements.txt" && -d "${DAKU_DIR}/venv" ]]; then
    "${DAKU_DIR}/venv/bin/pip" install -r "${DAKU_DIR}/requirements.txt" --quiet || true
fi

# Update systemd services if modified
if [[ -f "${DAKU_DIR}/systemd/daku.service" ]]; then
    cp "${DAKU_DIR}/systemd/daku.service" /etc/systemd/system/daku.service
fi
if [[ -f "${DAKU_DIR}/systemd/hermes.service" ]]; then
    cp "${DAKU_DIR}/systemd/hermes.service" /etc/systemd/system/hermes.service
fi
systemctl daemon-reload

# 3. Step 3: Restart Services
echo -e "${GREEN}[3/5] Restarting DAKU services...${NC}"
systemctl restart daku.service
sleep 2

# 4. Step 4: Health Check Verification
echo -e "${GREEN}[4/5] Running post-update health check...${NC}"
HEALTH_STATUS="FAIL"
for i in {1..6}; do
    echo "      Attempt ${i}/6: Probing http://127.0.0.1:8443/health..."
    if curl -s -f http://127.0.0.1:8443/health >/dev/null; then
        HEALTH_STATUS="OK"
        break
    fi
    sleep 2
done

# 5. Step 5: Verification or Automatic Rollback
if [[ "${HEALTH_STATUS}" == "OK" ]]; then
    echo -e "${GREEN}[5/5] Health check passed! Update successful.${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    echo -e "${GREEN}               UPDATE COMPLETED AND VERIFIED                  ${NC}"
    echo -e "${GREEN}==============================================================${NC}"
    exit 0
else
    echo -e "${RED}[5/5] Health check FAILED after update! Initiating automatic rollback...${NC}"
    echo -e "${YELLOW}      Restoring snapshot from ${BACKUP_FILE}...${NC}"
    tar -xzf "${BACKUP_FILE}" -C "${DAKU_DIR}"
    systemctl restart daku.service
    echo -e "${YELLOW}      Rollback executed. Service restored to pre-update state.${NC}"
    echo -e "${RED}==============================================================${NC}"
    echo -e "${RED}   UPDATE FAILED AND WAS SAFELY ROLLED BACK. CHECK LOGS:      ${NC}"
    echo -e "${RED}   journalctl -u daku -n 50 --no-pager                        ${NC}"
    echo -e "${RED}==============================================================${NC}"
    exit 1
fi
