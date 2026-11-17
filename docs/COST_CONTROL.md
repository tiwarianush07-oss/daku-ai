# DAKU + HERMES COST CONTROL POLICY & RESOURCE LIMITS

## 1. Zero-Cost Policy

DAKU adheres to a strict **Free-First Policy**:
> No paid services or subscriptions may ever be silently created. Every layer of the infrastructure must remain 100% free-of-charge under standard usage allowances.

---

## 2. Infrastructure Cost Breakdown

| Component | Provider & Tier | Maximum Free Allowance | DAKU Usage | Cost |
| :--- | :--- | :--- | :--- | :---: |
| **Compute VM** | Oracle Cloud Always Free (Ampere A1) | 4 OCPUs, 24 GB RAM | 2 OCPUs, 12 GB RAM | **₹0.00** |
| **Compute VM (Alternative)** | Oracle Cloud Always Free (AMD Micro) | 2 VMs, 1/8 OCPU, 1 GB RAM | 1 VM, 1 GB RAM | **₹0.00** |
| **Boot Volume Storage** | Oracle Cloud Always Free | 200 GB Total Block Volume | 50 GB Boot Volume | **₹0.00** |
| **Outbound Data Bandwidth** | Oracle Cloud Always Free | 10 TB / month | < 5 GB / month | **₹0.00** |
| **Public IPv4 Address** | Oracle Cloud Always Free | 1 Ephemeral IPv4 per VM | 1 Public IP | **₹0.00** |
| **Speech-to-Text (STT)** | Google Web Speech STT API / PyAudio | Unlimited personal voice queries | Push-to-Talk speech | **₹0.00** |
| **Text-to-Speech (TTS)** | Windows Native SAPI Synthesizer | Built-in Windows 11 OS engine | Spoken audio output | **₹0.00** |
| **Memory / Database** | Local SQLite (`~/.hermes/`) | Infinite local reads/writes | State & Context | **₹0.00** |
| **Hermes Agent Framework** | Open-source (Nous Research) | Apache 2.0 / Open Source | Agent gateway | **₹0.00** |
| **TOTAL MANDATORY MONTHLY COST** | — | — | — | **₹0.00 / mo** |

---

## 3. Optional Model API Spending (Pay-As-You-Go)

DAKU uses hosted cloud LLM providers. Several free-tier and low-cost options are supported:

| Provider | Model Name | Pricing Tier | Typical Cost for 1,000 Voice Queries |
| :--- | :--- | :--- | :--- |
| **Groq Cloud** | `llama-3.3-70b-versatile` | Free Tier available (Rate-limited) | **₹0.00 (Free)** |
| **OpenRouter** | `deepseek/deepseek-chat:free` | Free community models | **₹0.00 (Free)** |
| **DeepSeek API** | `deepseek-chat` | Paid Pay-As-You-Go ($0.14 / 1M tokens)| **~₹1.20 ($0.015)** |
| **Local Fallback** | Deterministic Intent Parser | Built-in offline regex & Windows APIs | **₹0.00 (Free)** |

---

## 4. How to Ensure ₹0 Bills on Oracle Cloud

To guarantee you are never billed by Oracle Cloud:
1. **Never Click "Upgrade to Paid Account"**: Always maintain the default **Always Free** account status.
2. **Keep Boot Volumes Under 200 GB**: When creating your compute instance, leave the boot volume size at default (47 GB or 50 GB). Do not specify > 200 GB.
3. **Set Up a Monthly Budget Alert**:
   - In Oracle Cloud Console, navigate to: **Billing & Cost Management** → **Budgets**.
   - Click **Create Budget**.
   - **Scope**: Entire Compartment / Tenancy.
   - **Target Monthly Amount**: `1.00` (e.g. ₹1 or $1).
   - **Alert Threshold**: `1%` (alerts you if any charge of ₹0.01 is incurred).
   - **Notification Email**: Your personal email.
4. **Do Not Attach Paid Add-ons**: Do not configure paid load balancers, enterprise NAT gateways, or high-performance GPU shapes.
