# DAKU + HERMES — FREE REMOTE HOSTING DEPLOYMENT GUIDE
**Target Infrastructure**: Oracle Cloud Always Free (Ubuntu Linux / ARM64 or x86)  
**Cost**: ₹0.00 / month forever  
**Laptop Role**: Lightweight Windows 11 voice/text client (< 15 MB RAM, 0% idle CPU)  
**Server Role**: Always-on headless DAKU brain + Hermes agent gateway  

---

## 1. Overview & Free-Tier Specifications

Oracle Cloud offers the most generous **Always Free** compute allocation in the cloud industry:

| Resource | Always Free Allowance | DAKU + Hermes Usage | Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Ampere A1 Compute (ARM64)** | Up to 4 OCPUs & 24 GB RAM | 2–4 OCPUs, 12–24 GB RAM | **₹0.00 (Free)** |
| **AMD Compute (x86)** | 2 VMs (1/8 OCPU, 1 GB RAM each)| Backup option | **₹0.00 (Free)** |
| **Block Storage** | 200 GB total boot/data storage | 50 GB boot volume | **₹0.00 (Free)** |
| **Outbound Data Transfer** | 10 TB per month | < 5 GB per month | **₹0.00 (Free)** |
| **IPv4 Address** | 1 Ephemeral / Reserved IPv4 | 1 Public IP | **₹0.00 (Free)** |

---

## 2. Step-by-Step Deployment Instructions

### Step 1: Create an Oracle Cloud Account
1. Visit [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
2. Sign up with your email and select your home region (choose the region geographically closest to you for lowest voice latency, e.g. Mumbai, Hyderabad, Singapore, or Frankfurt).
3. **Card Verification**: Oracle requires a valid credit/debit card for identity verification. A temporary pre-authorization hold (~₹80 / $1) is placed and immediately reversed. You will **never** be billed unless you manually upgrade to a paid account.

---

### Step 2: Create Your Free Ubuntu Compute Instance
1. In the Oracle Cloud Console, navigate to:  
   **Compute** → **Instances** → **Create Instance**.
2. **Name**: Enter `daku-server`.
3. **Image and Shape**:
   - Click **Edit Image and Shape**.
   - **Image**: Select **Ubuntu 24.04 LTS (Minimal or Standard)**.
   - **Shape**: Select **Ampere** (ARM-based Processor).
     - Number of OCPUs: `2` (or up to `4`).
     - Memory: `12 GB` (or up to `24 GB`).
     - *Note*: If Ampere is temporarily out of capacity in your chosen region, select **Specialty and previous generation** → **VM.Standard.E2.1.Micro** (1 OCPU, 1 GB RAM x86), which is also Always Free.
4. **Networking**: Select your default Virtual Cloud Network (VCN) and assign a public IPv4 address.
5. **Add SSH Keys**:
   - Choose **Generate a key pair for me** and click **Save Private Key** (saves as `ssh-key.key`), OR upload your existing public key.
6. Click **Create**. The instance will provision in 1–2 minutes and show status **RUNNING** with a public IP address.

---

### Step 3: Open Firewall Ports in Oracle VCN Security List
By default, Oracle Cloud blocks all ports except SSH (port 22). For production encrypted HTTPS traffic:
1. In the instance details page, click on your **Subnet** link under Primary VNIC.
2. Click on the **Default Security List for your VCN**.
3. Under **Ingress Rules**, click **Add Ingress Rules**:
   - Rule 1 (HTTPS):
     - **Source CIDR**: `0.0.0.0/0`
     - **IP Protocol**: `TCP`
     - **Destination Port Range**: `443`
     - **Description**: `DAKU Production HTTPS Gateway`
   - Rule 2 (HTTP / ACME Redirect):
     - **Source CIDR**: `0.0.0.0/0`
     - **IP Protocol**: `TCP`
     - **Destination Port Range**: `80`
     - **Description**: `HTTP to HTTPS Redirect & Certbot Challenge`
4. Click **Add Ingress Rules**.
*(Note: Internal port 8443 is bound strictly to loopback `127.0.0.1` and does not need to be opened in the VCN or UFW).*

---

### Step 4: Connect to Your Server via SSH
From your Windows 11 laptop, open PowerShell or Windows Terminal:

```powershell
# Connect to your server (replace with your server IP and key path)
ssh -i "path\to\ssh-key.key" ubuntu@<YOUR_SERVER_PUBLIC_IP>
```

---

### Step 5: Transfer DAKU Codebase & Run Automated Installer
You can clone your repository directly on the server or transfer the local files via `scp`:

```bash
# Clone directly onto server
git clone https://github.com/anush07/DAKU.git /opt/daku
cd /opt/daku

# Run the automated idempotent installer
sudo bash scripts/install_server.sh
```

The installer will:
1. Detect architecture (`aarch64` or `x86_64`).
2. Install Python 3, `uv`, `git`, `curl`, `ufw`, `nginx`, `openssl`, and `certbot`.
3. Install the official **Hermes Agent** (`NousResearch/hermes-agent`).
4. Create the unprivileged `daku` user.
5. Generate a high-entropy secret bearer token in `/etc/daku/daku.env`.
6. Configure Nginx reverse proxy terminating TLS on port 443 with HTTP (port 80) -> HTTPS 301 redirection.
7. Install and enable `daku.service`, `hermes.service`, and `nginx.service`.
8. Configure UFW firewall to allow only ports 22, 80, and 443.

---

### Step 6: Public Domain & Let's Encrypt Certificate (Optional / Recommended)
If you have a domain or dynamic DNS hostname pointing to your Oracle public IP:
```bash
sudo certbot --nginx -d daku.yourdomain.com
```
*Note: If testing without a domain, the installer automatically generates a 2048-bit RSA self-signed TLS certificate for immediate encrypted transport.*

---

### Step 7: Configure Cloud LLM Credentials
Edit the environment file on the server:

```bash
sudo nano /etc/daku/daku.env
```

Fill in your cloud model provider details (e.g. DeepSeek, OpenRouter, Groq):
```ini
MODEL_PROVIDER=deepseek
MODEL_NAME=deepseek-chat
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=sk-your-actual-api-key-here
```

Restart the server daemon to apply:
```bash
sudo systemctl restart daku
```

Check the health status:
```bash
bash scripts/health_check.sh
```

---

### Step 8: Configure Your Windows 11 Laptop Client
On your low-RAM Windows 11 laptop:
1. Open `c:\Users\anush07\Desktop\win10\DAKU\.env`.
2. Update the remote server parameters with your server's HTTPS URL and the `DAKU_AUTH_TOKEN` from Step 5:
   ```ini
   DAKU_SERVER_URL=https://<YOUR_SERVER_PUBLIC_IP_OR_DOMAIN>
   DAKU_AUTH_TOKEN=your_auth_token_from_server
   ```
3. Run the system diagnostics in remote mode:
   ```powershell
   py doctor.py --remote
   ```
   Verify that `Remote DAKU Server` reports `[OK] ONLINE` and `HTTPS / TLS Security` is verified.

---

### Step 9: Start DAKU
Run the lightweight client on your Windows 11 laptop:
```powershell
py client.py
```

Press **[Enter]** to speak or type commands. The laptop records the audio/text, passes it to the Oracle server over encrypted HTTPS (port 443), the server processes reasoning through the remote model router and Hermes agent, and returns the response for spoken output over your local Windows SAPI synthesizer.
