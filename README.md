# 📅 AWS Snapshot Lifecycle Physical Calendar Management System

A production-grade, enterprise-quality cloud backup automation system built with **Amazon EC2, EBS Snapshots, AWS Data Lifecycle Manager (DLM), AWS Lambda, and IAM (`LabRole`)** specifically optimized for **AWS Academy & Educate Learner Labs**.

---

## 🌟 Major Features & Highlights

1. **🗓️ Visual Physical Wall Calendar Grid:**
   * Full month calendar view (Monday–Sunday) showing every day of the month.
   * Color-coded badges for **Daily (24h)**, **Weekly (Sundays)**, **Monthly (1st of month)**, and **Blackout Freeze** windows.
   * Highlighted border for **Today**.

2. **⚡ 1-Click Auto-Repair / System Optimization:**
   * One button at the top that automatically detects expired snapshots, safely purges them, triggers missing daily backups, and instantly brings the system to **🟢 100% HEALTHY & COMPLIANT**.

3. **🔄 Disaster Recovery (DR) & Volume Restoration:**
   * Real-time Disaster Recovery Assessment Score (% DR Ready, RPO status < 24h).
   * **1-Click Volume Restore:** Select any snapshot and create a brand-new, active Amazon EBS volume in any Availability Zone!

4. **🚦 Real-Time Health Status Indicator (Green / Yellow / Red):**
   * 🟢 **GREEN (Healthy):** All backups completed, 0 errors, storage compliant.
   * 🟡 **YELLOW (Warning):** Expired snapshots pending purge.
   * 🔴 **RED (Critical):** Errors detected or budget ceiling threatened.

5. **📊 Storage Analytics & Formal Report Exporter:**
   * Interactive chart of Snapshots by Tier (Daily, Weekly, Monthly).
   * Storage cost metrics calculated at $0.05/GB/mo against the **$100 Learner Lab credit ceiling**.
   * One-click download of official **Audit & Compliance Reports** in **JSON** and **CSV** formats for assignment submission!

6. **🛡️ AWS Learner Lab `LabRole` Automated Compliance:**
   * Bypasses the common `iam:CreateRole` denial by dynamically utilizing the pre-provisioned `LabRole` (`arn:aws:iam::<Account>:role/LabRole`).

7. **🧪 Dual-Mode Operation (Live AWS Learner Lab + Mock Simulator):**
   * Fully functional offline mock simulator with persistent session state so you can test all features offline even when your lab session is stopped.

---

## 📁 Project Structure

```
aws-snapshot-lifecycle-calendar/
├── .vscode/
│   ├── launch.json              # Pre-configured F5 debug/run configurations
│   ├── tasks.json               # VS Code quick tasks
│   └── settings.json            # Editor and unit test settings
├── config/
│   ├── calendar_policy.json     # GFS schedules, blackout dates, & budget config
│   └── settings.py              # Configuration loader & environment variables
├── src/
│   ├── __init__.py
│   ├── aws_client.py            # Boto3 session, Learner Lab credential & LabRole handler
│   ├── calendar_engine.py       # Physical calendar math, monthly grid, & GFS logic
│   ├── snapshot_manager.py      # Snapshot creator, tagger, auditor, purger, & volume restorer
│   ├── cost_guard.py            # Budget tracker & EBS storage cost calculator
│   ├── dlm_manager.py           # AWS DLM policy payload builder & automator
│   ├── ec2_manager.py           # EC2 instance inspection & block device tagger
│   ├── iam_manager.py           # LabRole inspector & permissions verifier
│   ├── lambda_function.py       # Serverless Lambda calendar engine
│   ├── lambda_manager.py        # Lambda deployer & EventBridge scheduler
│   └── mock_provider.py         # Realistic mock AWS provider for offline testing
├── app.py                       # Modern Streamlit Web Dashboard
├── cli.py                       # Full-featured command-line interface
├── test_project.py              # 16 automated unit tests (100% pass offline)
├── requirements.txt             # Python dependencies
├── .env.example                 # Credentials template for AWS Learner Lab
└── README.md                    # Project documentation & assignment guide
```

---

## 🚀 Quickstart in Visual Studio Code

### Step 1: Open Project in VS Code
Open VS Code, click **File** $\rightarrow$ **Open Folder...**, and select:
`C:\Users\karri\.gemini\antigravity\scratch\aws-snapshot-lifecycle-calendar`

### Step 2: Set Up Virtual Environment & Dependencies
Open the VS Code Terminal (`Ctrl + \``):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 3: Configure AWS Learner Lab Credentials
1. In your AWS Learner Lab console, click **AWS Details** $\rightarrow$ **Show AWS CLI credentials**.
2. Save them into `.env` (or simply paste the whole block directly into the dashboard sidebar!):
   ```ini
   AWS_DEFAULT_REGION=us-east-1
   AWS_ACCESS_KEY_ID=ASIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_SESSION_TOKEN=IQoJb3Jp...
   AWS_LAB_ROLE_NAME=LabRole
   MOCK_AWS=false
   ```

### Step 4: Launch the Dashboard
Press **F5** in VS Code (or run in terminal):
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## ⌨️ CLI Commands Reference

```bash
# 1. View status, volumes, and Learner Lab budget
python cli.py status

# 2. View 14-day calendar schedule forecast
python cli.py forecast --days 14

# 3. Run today's scheduled physical calendar backups
python cli.py run-schedule

# 4. Audit retention and list expired snapshots
python cli.py audit

# 5. Preview deletion of expired snapshots (Safe Dry-Run)
python cli.py purge --dry-run

# 6. Execute permanent deletion of expired snapshots
python cli.py purge --force

# 7. Restore an EBS volume from a snapshot (Disaster Recovery)
python cli.py restore snap-0001dailyexpired --az us-east-1a

# 8. Evaluate Disaster Recovery Readiness Score
python cli.py dr-assessment

# 9. Deploy AWS Data Lifecycle Manager policy using LabRole
python cli.py deploy-dlm
```

---

## 🧪 Automated Unit Testing

Run the included automated test suite in VS Code:
```bash
python -m unittest test_project.py
```
*(All 16 unit tests execute offline in mock mode and pass in < 0.02s).*
