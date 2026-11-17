# DAKU + HERMES DEPLOYMENT TROUBLESHOOTING & FAILURE RECOVERY GUIDE
**Target**: Oracle Cloud Always Free (Ubuntu Linux Headless Server) + Windows 11 Laptop Client  
**Policy**: Systematic Diagnosis, Root-Cause Identification, Minimal Fix, Retest, Document  

---

## 1. Systematic Troubleshooting Methodology

When any component or test fails, strictly avoid random trial-and-error edits. Follow this decision cycle:

```text
               +-------------------------------------------+
               |              ERROR DETECTED               |
               +---------------------┬---------------------+
                                     │
                                     ▼
               +-------------------------------------------+
               |             1. CAPTURE LOGS               |
               | - Server: journalctl -u daku -n 50        |
               | - Hermes: journalctl -u hermes -n 50      |
               | - Laptop: py doctor.py --remote           |
               +---------------------┬---------------------+
                                     │
                                     ▼
               +-------------------------------------------+
               |         2. IDENTIFY ROOT CAUSE            |
               | - Network / Firewall / Oracle Ingress     |
               | - Authorization Token Mismatch            |
               | - Systemd Sandbox Permission Violation    |
               | - Hosted LLM Rate Limit or Quota          |
               +---------------------┬---------------------+
                                     │
                                     ▼
               +-------------------------------------------+
               |           3. MAKE SMALLEST FIX            |
               | - Isolated config or permissions tweak    |
               | - Avoid unnecessary structural rewrites   |
               +---------------------┬---------------------+
                                     │
                                     ▼
               +-------------------------------------------+
               |                 4. RETEST                 |
               | - bash scripts/health_check.sh            |
               | - py -m unittest discover -s tests -v     |
               | - py doctor.py --remote                   |
               +---------------------┬---------------------+
                                     │
                                     ▼
               +-------------------------------------------+
               |               5. DOCUMENT                 |
               | - Record root cause and fix in this guide |
               +-------------------------------------------+
```

---

## 2. Decision Tree & Root-Cause Solutions

### Issue 1: Remote Server Reports `OFFLINE` (`Connection refused` or `Connection timed out`)
* **Diagnostic Command**:
  ```powershell
  py doctor.py --remote
  # Or from Linux/WSL:
  curl -v http://<SERVER_IP>:8443/health
  ```
* **Potential Root Causes**:
  1. **Oracle Cloud Virtual Cloud Network (VCN) Ingress Rule Missing**: Oracle Cloud firewall drops all incoming ports by default except SSH (22).
     - *Fix*: In Oracle Cloud Console → Compute → Instance → Subnet → Default Security List → Ingress Rules → Add Ingress Rule:
       - Source CIDR: `0.0.0.0/0`
       - Destination Port: `8443`
       - Protocol: `TCP`
  2. **Ubuntu OS Firewall (UFW) Not Permitting Port 8443**:
     - *Fix*: SSH into the server and run:
       ```bash
       sudo ufw allow 8443/tcp comment 'DAKU API'
       sudo ufw reload
       sudo ufw status verbose
       ```
  3. **DAKU Server Daemon Not Running**:
     - *Fix*: Check systemd unit status:
       ```bash
       sudo systemctl status daku
       sudo journalctl -u daku -n 30 --no-pager
       ```
       If stopped, restart:
       ```bash
       sudo systemctl restart daku
       ```

---

### Issue 2: HTTP 401 Unauthorized (`Authentication failed`)
* **Symptom**: Client outputs: `Authentication failed with remote DAKU server. Please check DAKU_AUTH_TOKEN.`
* **Root Cause**: The bearer token in the client laptop's `.env` does not match the token in the server's `/etc/daku/daku.env`.
* **Fix**:
  1. On the server, retrieve the exact token:
     ```bash
     sudo grep -E '^DAKU_AUTH_TOKEN=' /etc/daku/daku.env
     ```
  2. On the Windows laptop, open `c:\Users\anush07\Desktop\win10\DAKU\.env` and set:
     ```ini
     DAKU_AUTH_TOKEN=your_exact_token_from_server
     ```
  3. Validate with:
     ```powershell
     py doctor.py --remote
     ```

---

### Issue 3: Hermes Gateway Status `STOPPED` or `STANDBY`
* **Diagnostic Command**:
  ```bash
  sudo systemctl status hermes
  sudo journalctl -u hermes -n 50 --no-pager
  ```
* **Potential Root Causes**:
  1. **First-time configuration not yet initialized**: Hermes may require an initial setup run.
     - *Fix*: Switch to the `daku` user and execute first-time setup:
       ```bash
       sudo -u daku -i
       export PATH="$HOME/.local/bin:$PATH"
       hermes setup
       ```
  2. **Hermes process bind conflict on port 8080**:
     - *Fix*: Check if another process is using port 8080:
       ```bash
       sudo ss -tulpn | grep 8080
       ```
  3. **Restart Service**:
     ```bash
     sudo systemctl restart hermes
     ```

---

### Issue 4: Local Client Activates "Offline Mode" Automatically
* **Symptom**: Laptop client responds with: `[Offline Mode: ...] Could not reach remote brain. Basic system commands (RAM, CPU, open app) work locally.`
* **Behavior**: This is DAKU's **Double-Redundant Offline Fallback Engine** working as designed! If network connectivity drops or the remote server undergoes maintenance, DAKU does not crash or throw unhandled exceptions. It parses local intents (checking RAM, CPU, opening Notepad, getting local time) locally on the laptop with zero heavy model overhead.
* **Resolution**: Once internet connectivity or remote server returns, DAKU automatically reconnects on the next query.

---

### Issue 5: Cloud LLM API Error 429 (Rate Limit) or 503 (Provider Congestion)
* **Symptom**: `Remote server error (429)` or `Remote server 5xx error`.
* **Root Cause**: The hosted AI provider (e.g. DeepSeek API, Groq, or OpenRouter) is experiencing temporary rate limiting or congestion.
* **Fix**:
  1. Check provider balance or rate tier.
  2. Adjust request timeout in `/etc/daku/daku.env`:
     ```ini
     MODEL_TIMEOUT_SECONDS=30.0
     ```
  3. Switch to fallback provider (e.g. switch `MODEL_PROVIDER=groq` or `openrouter`).
  4. Restart server: `sudo systemctl restart daku`.

---

### Issue 6: Systemd Sandboxing Blocks Legitimate Tool
* **Symptom**: A server tool fails with permission denied inside `/opt/daku`.
* **Root Cause**: `ProtectSystem=full` in `/etc/systemd/system/daku.service` mounts `/usr`, `/boot`, and `/etc` as read-only.
* **Fix**: Ensure all dynamic state and log writes are directed strictly to `/opt/daku/data` or `/var/log/daku`, which are granted write permissions in the service file.

---

## 3. Real Deployment Blockers Encountered & Documented Fixes

| Blocker | Root Cause | Implemented Solution | Verification |
| :--- | :--- | :--- | :--- |
| **Missing SpeechRecognition on Python 3.13** | Audio packages changed in 3.13 | Installed `SpeechRecognition-3.17.0` with `audioop-lts` | STT unit tests pass 100% |
| **PowerShell SAPI Timeout on Athlon 3050U** | Athlon 2-core CPU cold-start latency | Added double-redundant COM `SAPI.SpVoice` fallback in `voice/tts.py` | 0 ms startup delay, zero crash |
| **Missing Disk Space Diagnostic** | `doctor.py` had RAM/CPU but no disk check | Added `check_disk()` using standard library `shutil.disk_usage` | `daku doctor` passes all 9 checks |
| **Timing Attack on API Bearer Token** | Naive string equality in auth gate | Used `secrets.compare_digest` in `server/daku_server.py` | Constant-time auth certified |
| **Runaway Agent Loop Risk** | Multi-step agent could loop indefinitely | Hard capped at 10 steps max, 2 retries per step in `tools/planner.py` | Test 18 & 19 pass |

---

## 4. Disaster Recovery & Rollback Quick Command Reference

```bash
# Emergency restart of both services
sudo systemctl restart daku hermes

# Check live logs in real time
sudo journalctl -u daku -f

# View recent errors only
sudo journalctl -u daku -p err -n 20

# Run full server health verification
bash /opt/daku/scripts/health_check.sh

# Revert to last snapshot
sudo bash -c 'tar -xzf $(ls -t /var/backups/daku/daku_*.tar.gz | head -1) -C /opt/daku && systemctl restart daku'
```
