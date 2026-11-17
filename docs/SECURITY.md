# DAKU + HERMES SECURITY POLICY & ARCHITECTURE

## 1. Security Principles

DAKU enforces a zero-trust model between the AI reasoning layer and the host operating system. The model is treated as an untrusted reasoning planner that proposes actions; it **never directly executes operating system commands**.

### Core Guarantees
1. **Zero Raw Shell Execution**: The agent cannot execute arbitrary bash, cmd.exe, or PowerShell commands.
2. **Deterministic Allowlisting**: Only tools registered in `ToolRegistry` with validated schemas can be executed.
3. **Strict 3-Tier Permissions**: Actions are classified into `SAFE`, `CONFIRMATION_REQUIRED`, or `BLOCKED`.
4. **Credential Isolation & Redaction**: Secrets (API keys, tokens, passwords) are masked in all logs and outputs.
5. **Least-Open Network Perimeter**: Only SSH (port 22) and the authenticated DAKU port (8443) are allowed.

---

## 2. 3-Tier Permission Hierarchy

```text
                                 Tool Call Proposed
                                         │
                                         ▼
                             [PermissionManager.evaluate]
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 ▼                       ▼                       ▼
            [ BLOCKED ]     [ CONFIRMATION_REQUIRED ]       [ SAFE ]
                 │                       │                       │
         Permanent Refusal       Prompt User on Client     Immediate Execution
         Log Alert               Wait for Approval         Post-verification
```

### Classification Rules

#### Tier 1: SAFE (Pre-approved)
Operations that are read-only, non-destructive, and pose zero risk of data loss:
- Conversational chat and reasoning.
- Hardware queries (RAM, CPU, disk free space, local time, network status).
- Safe file reading, directory listing, and file searching within allowlisted directories.
- Browser URL navigation and reading page title/text.

#### Tier 2: CONFIRMATION_REQUIRED
Operations that modify files, perform form submissions, or trigger state changes:
- Creating files or writing contents to disk.
- Submitting interactive forms or clicking sensitive web elements.
- Launching heavy desktop applications.
- **Workflow**: DAKU pauses execution, issues a security prompt to the Windows client, and requires explicit user consent (`y/N`) before proceeding.

#### Tier 3: BLOCKED (Permanently Refused)
Operations that are strictly prohibited by policy and can never be executed under any circumstances:
- Arbitrary shell commands (`cmd.exe`, `powershell.exe`, `bash`, `sh`, `eval`).
- File or directory deletion (`rmdir`, `delete_file`, `unlink`, `remove`).
- Disk formatting or partition modification.
- Database dropping (`drop table`, `drop database`).
- Credential dumping or reading environment secrets (`read_env_secrets`, `dump_credentials`).
- System reboot, shutdown, or power state modification.

---

## 3. Remote Server Hardening (Oracle Cloud)

### Firewall Configuration (UFW) & Reverse Proxy (Port 443)
The server firewall is configured with default deny incoming policies, exposing only SSH and encrypted HTTPS:
```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH Key Access'
ufw allow 80/tcp comment 'HTTP Redirect / Certbot ACME'
ufw allow 443/tcp comment 'DAKU HTTPS API (Nginx Reverse Proxy)'
ufw enable
```
*Note*: Direct public access to port 8443 is blocked. DAKU Server binds to `127.0.0.1:8443`, and all client communication is encrypted over TLS on port 443 via Nginx.

### TLS / HTTPS Encryption
- Transport encryption enforced via Nginx TLS reverse proxy on port 443.
- Supported protocols: `TLSv1.2` and `TLSv1.3` with high-security ciphers (`HIGH:!aNULL:!MD5`).
- Automatic HTTP to HTTPS 301 redirection on port 80.
- Automated Let's Encrypt renewal configured via `certbot`.

### Systemd Sandboxing
The `daku.service` daemon runs under unprivileged user `daku` with Linux kernel namespaces:
- `NoNewPrivileges=true`: Disallows privilege escalation (e.g. via setuid binaries).
- `ProtectSystem=full`: Mounts `/usr`, `/boot`, and `/etc` as read-only for the service.
- `PrivateTmp=true`: Isolates `/tmp` from the host system.
- `ProtectKernelTunables=true`: Disallows altering kernel parameters (`/proc/sys`).
- `ProtectKernelModules=true`: Prevents kernel module loading.
- `MemoryMax=512M`: Hard limit on memory usage to prevent denial-of-service.

### Authentication & Token Protection
- All calls to `/api/chat`, `/api/confirm`, and `/api/status` require an `Authorization: Bearer <TOKEN>` header.
- Token validation uses `secrets.compare_digest` to prevent side-channel timing attacks.
- The environment configuration file (`/etc/daku/daku.env`) is protected with `chmod 600` and owned exclusively by `daku:daku`.
- The `GET /health` endpoint exposes high-level status only, with zero secrets or internal paths.
