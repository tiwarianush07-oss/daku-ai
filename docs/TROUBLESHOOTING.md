# DAKU + HERMES DEPLOYMENT TROUBLESHOOTING GUIDE

## 1. Quick Diagnostic Flowchart

```text
[ Symptom: DAKU Not Responding or Error Encountered ]
                      │
                      ▼
            Run Diagnostic Suite on Laptop:
               py doctor.py --remote
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
[ Remote Server: OFFLINE ]   [ Remote Server: ONLINE ]
        │                           │
        │                           ├── HTTP 401: Token mismatch in .env
        │                           ├── Hermes Inactive: Check hermes.service
        │                           └── Audio Error: Check Windows Mic permissions
        │
        ├── Step 1: Check VM state in Oracle Cloud Console (must be RUNNING)
        ├── Step 2: Check Oracle VCN Ingress Rules (port 8443 TCP allowed)
        ├── Step 3: Check Server UFW (sudo ufw status)
        └── Step 4: Check Service status (sudo systemctl status daku)
```

---

## 2. Common Issues & Solutions

### Issue 1: `Remote server unreachable (Connection refused or timed out)`
* **Cause**: Oracle VCN Security List has not permitted port 8443, or the server firewall (UFW) is blocking traffic.
* **Resolution**:
  1. SSH into the server:
     ```bash
     ssh -i key.key ubuntu@<SERVER_IP>
     ```
  2. Verify that `daku.service` is actively running:
     ```bash
     sudo systemctl status daku
     ```
  3. Verify that UFW allows port 8443:
     ```bash
     sudo ufw status verbose
     # If missing:
     sudo ufw allow 8443/tcp
     ```
  4. In the Oracle Cloud Console, navigate to your instance's **Virtual Cloud Network (VCN)** → **Security Lists** → **Default Security List**, and confirm an Ingress rule exists for `Destination Port: 8443, Protocol: TCP, Source: 0.0.0.0/0`.

---

### Issue 2: `Authentication failed: Please check DAKU_AUTH_TOKEN` (HTTP 401)
* **Cause**: The `DAKU_AUTH_TOKEN` in your laptop's `.env` does not match `/etc/daku/daku.env` on the server.
* **Resolution**:
  1. Print the server's configured token:
     ```bash
     sudo grep -E '^DAKU_AUTH_TOKEN=' /etc/daku/daku.env
     ```
  2. Copy that value into your Windows laptop's `.env` file:
     ```ini
     DAKU_AUTH_TOKEN=the_exact_token_from_server
     ```
  3. Rerun `py doctor.py --remote` to verify authorization.

---

### Issue 3: `Microphone unavailable; Text Fallback Active`
* **Cause**: Microphone is not plugged in, or Windows 11 privacy settings block microphone access.
* **Resolution**:
  1. Open Windows **Settings** → **Privacy & Security** → **Microphone**.
  2. Ensure **Microphone access** and **Let apps access your microphone** are turned **ON**.
  3. Note that DAKU works 100% reliably in console mode even without a microphone: you can simply type your commands when prompted.

---

### Issue 4: `Hermes Agent Gateway: INACTIVE`
* **Cause**: Hermes service failed to start or is waiting for first-time configuration.
* **Resolution**:
  1. Inspect the service logs:
     ```bash
     sudo journalctl -u hermes -n 50 --no-pager
     ```
  2. If Hermes requires first-time setup, run:
     ```bash
     sudo -u daku -i
     hermes setup
     ```
  3. Restart the service:
     ```bash
     sudo systemctl restart hermes
     ```

---

### Issue 5: Cloud LLM API Timeout or 429 Rate Limit
* **Cause**: The hosted model endpoint (DeepSeek, Groq, or OpenRouter) is experiencing congestion or your API key has exhausted its rate quota.
* **Resolution**:
  1. Verify your API key and balance at your provider's dashboard.
  2. Increase timeout in `/etc/daku/daku.env`:
     ```ini
     MODEL_TIMEOUT_SECONDS=30.0
     ```
  3. Restart DAKU:
     ```bash
     sudo systemctl restart daku
     ```
  4. Note that DAKU automatically activates local offline fallback if the cloud model is unreachable.
