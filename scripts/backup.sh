#!/usr/bin/env bash
# ==============================================================================
# DAKU + HERMES — LIGHTWEIGHT STATE & CONFIGURATION BACKUP SCRIPT
# Backs up configuration, SQLite state, and logs with automatic rotation
# ==============================================================================

set -euo pipefail

BACKUP_DIR="/var/backups/daku"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="daku_state_backup_${TIMESTAMP}.tar.gz"
TARGET="${BACKUP_DIR}/${ARCHIVE_NAME}"

mkdir -p "${BACKUP_DIR}"

echo "[DAKU Backup] Starting state snapshot at $(date)..."

# Collect list of existing directories to backup
BACKUP_ITEMS=()
if [[ -d "/etc/daku" ]]; then
    BACKUP_ITEMS+=("/etc/daku")
fi
if [[ -d "/home/daku/.hermes" ]]; then
    BACKUP_ITEMS+=("/home/daku/.hermes")
fi
if [[ -d "/opt/daku/data" ]]; then
    BACKUP_ITEMS+=("/opt/daku/data")
fi

if [[ ${#BACKUP_ITEMS[@]} -eq 0 ]]; then
    echo "[DAKU Backup] No state directories found to backup."
    exit 0
fi

# Create compressed archive
tar -czf "${TARGET}" "${BACKUP_ITEMS[@]}" 2>/dev/null || true
chmod 600 "${TARGET}"

SIZE=$(du -h "${TARGET}" | cut -f1)
echo "[DAKU Backup] Backup saved: ${TARGET} (${SIZE})"

# Retain only the last 7 backups to preserve disk space on Always Free VM
echo "[DAKU Backup] Rotating old backups (keeping newest 7)..."
find "${BACKUP_DIR}" -name "daku_state_backup_*.tar.gz" -type f | sort -r | tail -n +8 | xargs -r rm -f

echo "[DAKU Backup] Completed successfully."
