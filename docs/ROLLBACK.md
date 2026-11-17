# DAKU + HERMES ROLLBACK & DISASTER RECOVERY PROCEDURES

## 1. Overview

This document defines deterministic rollback procedures for both the remote server and the local Windows 11 client to recover immediately from failed updates, configuration corruption, or network outages.

---

## 2. Server-Side Rollback Procedures

### Scenario A: Automatic Rollback (Built into `update_server.sh`)
When running `scripts/update_server.sh`, an automated snapshot is created before any files are modified. If the post-update health check fails, the script automatically restores the snapshot and restarts the service:
```bash
# Automatic rollback triggers if /health returns non-200
# Output:
# [5/5] Health check FAILED after update! Initiating automatic rollback...
# Restoring snapshot from /var/backups/daku/daku_pre_update_YYYYMMDD_HHMMSS.tar.gz...
```

---

### Scenario B: Manual Server Rollback
If you need to manually revert the server to a previous working snapshot:

1. List available snapshots:
   ```bash
   ls -la /var/backups/daku/
   ```
2. Stop the running service:
   ```bash
   sudo systemctl stop daku
   ```
3. Restore the desired snapshot:
   ```bash
   # Replace with your desired backup timestamp
   sudo tar -xzf /var/backups/daku/daku_state_backup_YYYYMMDD_HHMMSS.tar.gz -C /
   ```
4. Restart the services:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart daku nginx
   ```
5. Verify health:
   ```bash
   bash /opt/daku/scripts/health_check.sh
   ```

---

## 3. Client-Side Rollback (Windows 11 Laptop)

If your remote server is down, decommissioned, or undergoing maintenance, you can run DAKU locally without relying on the remote host:

### Option 1: Client Built-in Offline Fallback
Simply start the client:
```powershell
py client.py
```
If the server is offline, the client detects this within 4 seconds and automatically falls back to local deterministic intent parsing without crashing.

### Option 2: Standalone Local Mode (`main.py`)
To run DAKU completely standalone (as in Phase 4):
```powershell
py main.py
```
In `main.py`, DAKU runs the local in-process `Brain`, `TaskPlanner`, and `ToolRegistry` directly on your Windows laptop.

---

## 4. Emergency Reset

If server configuration files are deleted or corrupted:
```bash
# Re-run the idempotent installer to restore default files and services
sudo bash /opt/daku/scripts/install_server.sh
```
The installer will automatically detect missing files, regenerate systemd service definitions, and restart DAKU cleanly.
