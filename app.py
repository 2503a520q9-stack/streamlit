"""
Streamlit Web Dashboard: AWS Snapshot Lifecycle Physical Calendar
Enterprise-grade, ultra-attractive user interface for AWS Learner Lab.
Implements Amazon EC2, EBS Snapshots, AWS Data Lifecycle Manager (DLM), AWS Lambda, and IAM (LabRole).
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import io

from config.settings import load_policy_config, save_policy_config
from src.aws_client import AWSClientManager
from src.calendar_engine import CalendarEngine
from src.snapshot_manager import SnapshotManager
from src.cost_guard import CostGuard
from src.dlm_manager import DLMManager
from src.iam_manager import IAMManager
from src.ec2_manager import EC2Manager

st.set_page_config(
    page_title="AWS Snapshot Lifecycle Physical Calendar",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------- CUSTOM CSS STYLING ----------------- #
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .status-banner-green {
        background: linear-gradient(90deg, #134e5e, #71b280);
        color: white;
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(113, 178, 128, 0.3);
    }
    .status-banner-yellow {
        background: linear-gradient(90deg, #b79891, #94716b);
        color: white;
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(183, 152, 145, 0.3);
    }
    .status-banner-red {
        background: linear-gradient(90deg, #cb2d3e, #ef473a);
        color: white;
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(239, 71, 58, 0.3);
    }
    .cal-day-cell {
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 8px;
        min-height: 80px;
        background: rgba(255,255,255,0.02);
    }
    .cal-today {
        border: 2px solid #38ef7d !important;
        background: rgba(56, 239, 125, 0.1) !important;
    }
    .badge-daily {
        background-color: #2196F3;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin: 2px;
    }
    .badge-weekly {
        background-color: #9C27B0;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin: 2px;
    }
    .badge-monthly {
        background-color: #FF9800;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin: 2px;
    }
    .badge-blackout {
        background-color: #E91E63;
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 4px;
        display: inline-block;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- SESSION STATE & INITIALIZATION ----------------- #
if "policy_config" not in st.session_state:
    st.session_state.policy_config = load_policy_config()

# Pre-load credentials from .env
env_key = st.session_state.get("env_key") or ""
env_secret = st.session_state.get("env_secret") or ""
env_token = st.session_state.get("env_token") or ""

import os
if not env_key:
    env_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("aws_access_key_id") or ""
    env_secret = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("aws_secret_access_key") or ""
    env_token = os.getenv("AWS_SESSION_TOKEN") or os.getenv("aws_session_token") or ""

has_env_credentials = bool(env_key and env_secret and "XXXXX" not in env_key)

# ----------------- SIDEBAR ----------------- #
st.sidebar.title("☁️ AWS Learner Lab Setup")

use_mock = st.sidebar.checkbox(
    "Run in Mock Simulator Mode",
    value=st.session_state.get("use_mock", not has_env_credentials),
    help="Toggle offline simulation mode."
)
st.session_state.use_mock = use_mock

with st.sidebar.expander("🔑 AWS Learner Lab Credentials", expanded=not use_mock and not has_env_credentials):
    if has_env_credentials and not use_mock:
        st.success("✅ Credentials auto-loaded from `.env` file!")
    else:
        st.caption("Paste the full text from AWS Details (or enter individually):")

    raw_block = st.text_area(
        "📋 Quick Paste: Entire AWS CLI Block",
        height=90,
        placeholder="[default]\naws_access_key_id=ASIA...\naws_secret_access_key=...\naws_session_token=IQoJ..."
    )

    parsed_key, parsed_secret, parsed_token = None, None, None
    if raw_block:
        for line in raw_block.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "aws_access_key_id": parsed_key = v
                elif k == "aws_secret_access_key": parsed_secret = v
                elif k == "aws_session_token": parsed_token = v
            elif parsed_token and not line.startswith("["):
                parsed_token += line

    final_key = parsed_key or env_key
    final_secret = parsed_secret or env_secret
    final_token = parsed_token or env_token

    aws_key = st.text_input("AWS Access Key ID", value=final_key, type="password", key="aws_key")
    aws_secret = st.text_input("AWS Secret Access Key", value=final_secret, type="password", key="aws_secret")
    aws_token = st.text_area("AWS Session Token", value=final_token, height=80, key="aws_token")
    aws_region = st.selectbox("AWS Region", ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"], index=0)
    connect_btn = st.button("Connect / Refresh AWS Session", use_container_width=True)

# Initialize AWS Client (Persisted in st.session_state so deletions & creates stay active!)
client_key = f"{aws_key}_{aws_secret}_{aws_token}_{aws_region}_{use_mock}"
if "aws_client" not in st.session_state or st.session_state.get("_last_client_key") != client_key or connect_btn:
    st.session_state.aws_client = AWSClientManager(
        access_key=aws_key if aws_key else None,
        secret_key=aws_secret if aws_secret else None,
        session_token=aws_token if aws_token else None,
        region=aws_region,
        force_mock=use_mock
    )
    st.session_state._last_client_key = client_key

aws_client = st.session_state.aws_client
calendar_engine = CalendarEngine(st.session_state.policy_config)
snapshot_manager = SnapshotManager(aws_client, calendar_engine, st.session_state.policy_config)
cost_guard = CostGuard(
    total_budget_usd=st.session_state.policy_config.get("budget_guard", {}).get("learner_lab_total_budget_usd", 100.0),
    ebs_cost_per_gb_month=st.session_state.policy_config.get("budget_guard", {}).get("ebs_cost_per_gb_month", 0.05),
    alert_threshold_usd=st.session_state.policy_config.get("budget_guard", {}).get("alert_threshold_usd", 5.0)
)
dlm_manager = DLMManager(aws_client, st.session_state.policy_config)
iam_manager = IAMManager(aws_client)
ec2_manager = EC2Manager(aws_client)

# Status Badge in Sidebar
conn_info = aws_client.get_connection_info()
if conn_info["is_mock"]:
    st.sidebar.warning(f"🧪 Mode: **Simulator / Mock Mode**\n\n_{conn_info['reason']}_")
else:
    st.sidebar.success(f"🟢 Connected to **AWS Learner Lab**\n* Account: `{conn_info['account_id']}`\n* Role: `LabRole`\n* Region: `{conn_info['region']}`")

# ----------------- BUDGET GUARD IN SIDEBAR ----------------- #
snapshots_list = snapshot_manager.list_managed_snapshots()
audit_info = snapshot_manager.audit_retention()
cost_metrics = cost_guard.calculate_snapshot_costs(
    snapshots_list,
    expired_count=audit_info["expired_count"],
    expired_gb=audit_info["expired_total_gb"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("💰 $100 Learner Lab Budget Guard")
budget_pct = min(1.0, cost_metrics["budget_used_percentage"] / 100.0)
st.sidebar.progress(budget_pct, text=f"{cost_metrics['budget_used_percentage']}% of $100 Used")
st.sidebar.caption(f"Estimated Storage Bill: **${cost_metrics['monthly_cost_usd']} / month** ({cost_metrics['total_gb']} GB total)")

# ----------------- SYSTEM HEALTH EVALUATION ----------------- #
status_counts = {"completed": 0, "pending": 0, "error": 0}
for s in snapshots_list:
    st_val = str(s.get("State", "completed")).lower()
    if "error" in st_val or "fail" in st_val:
        status_counts["error"] += 1
    elif "pending" in st_val:
        status_counts["pending"] += 1
    else:
        status_counts["completed"] += 1

if snapshots_list:
    latest_snap = snapshots_list[0]
    latest_time_str = str(latest_snap.get("StartTime", "N/A"))
    latest_time_formatted = latest_time_str.split(".")[0].replace("T", " ") + " UTC"
else:
    latest_time_formatted = "No snapshots yet"

today = date.today()
today_tiers = calendar_engine.get_applicable_tiers_for_date(today)
if today_tiers:
    next_sched_str = f"Today ({today.strftime('%b %d')}) at {today_tiers[0]['time_utc']} UTC [{', '.join([t['tier'] for t in today_tiers])}]"
else:
    tomorrow = today + timedelta(days=1)
    tomorrow_tiers = calendar_engine.get_applicable_tiers_for_date(tomorrow)
    next_sched_str = f"Tomorrow ({tomorrow.strftime('%b %d')}) at {tomorrow_tiers[0]['time_utc']} UTC" if tomorrow_tiers else "Scheduled on Calendar"

# Evaluate Health
if status_counts["error"] > 0:
    health_status = "RED"
    health_badge = "🔴 CRITICAL / ACTION REQUIRED"
    health_message = f"Found {status_counts['error']} snapshot(s) in ERROR state! Check EC2 permissions."
    banner_class = "status-banner-red"
elif audit_info["expired_count"] > 3 or cost_metrics["status"] == "DANGER":
    health_status = "RED"
    health_badge = "🔴 HIGH OVERDUE STORAGE"
    health_message = f"Storage threshold warning: {audit_info['expired_count']} expired snapshots overdue for deletion!"
    banner_class = "status-banner-red"
elif audit_info["expired_count"] > 0 or cost_metrics["status"] == "WARNING":
    health_status = "YELLOW"
    health_badge = "🟡 ATTENTION NEEDED"
    health_message = f"{audit_info['expired_count']} snapshot(s) past expiration date. Click 'Auto-Repair' to purge."
    banner_class = "status-banner-yellow"
elif not snapshots_list:
    health_status = "YELLOW"
    health_badge = "🟡 NO SNAPSHOTS YET"
    health_message = "No managed snapshots found. Click 'Auto-Repair' to take today's initial backup."
    banner_class = "status-banner-yellow"
else:
    health_status = "GREEN"
    health_badge = "🟢 HEALTHY & COMPLIANT"
    health_message = "All physical calendar schedules, retention rules, and budget limits are 100% compliant."
    banner_class = "status-banner-green"

# ----------------- MAIN TITLE & STATUS BANNER ----------------- #
st.title("📅 AWS Snapshot Lifecycle Physical Calendar")
st.caption("Amazon EC2 • EBS Snapshots • AWS Data Lifecycle Manager (DLM) • AWS Lambda • IAM (`LabRole`)")

# Colored Health Status Indicator Banner with 1-Click Auto-Repair
col_b1, col_b2 = st.columns([4, 1.2])
with col_b1:
    st.markdown(f"""
    <div class="{banner_class}">
        <h3 style="margin:0; padding:0;">{health_badge}</h3>
        <p style="margin:6px 0 0 0; font-size:15px; opacity:0.95;"><b>System Health:</b> {health_message}</p>
    </div>
    """, unsafe_allow_html=True)

with col_b2:
    if st.button("⚡ 1-Click Auto-Repair", type="primary", use_container_width=True, help="Automatically purges expired snapshots and triggers missing backups to achieve Green Health!"):
        # 1. Purge expired
        if audit_info["expired_count"] > 0:
            snapshot_manager.purge_expired_snapshots(dry_run=False)
        # 2. Run today's backup if none today
        snapshot_manager.run_calendar_lifecycle(today)
        st.toast("🎉 Auto-Repair Completed! System is now 100% Green & Compliant.")
        st.rerun()

# ----------------- TOP METRICS ROW ----------------- #
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric(
        label="📊 Total Snapshots Created",
        value=len(snapshots_list),
        delta=f"{status_counts['completed']} Completed"
    )
with col_m2:
    st.metric(
        label="🕒 Latest Snapshot Time",
        value=latest_time_formatted.split(" ")[0] if " " in latest_time_formatted else latest_time_formatted,
        delta=latest_time_formatted.split(" ")[1] if " " in latest_time_formatted else ""
    )
with col_m3:
    st.metric(
        label="⏰ Next Scheduled Backup",
        value=next_sched_str.split(" [")[0],
        delta=f"Tiers: {next_sched_str.split('[')[-1].replace(']', '')}" if "[" in next_sched_str else None
    )
with col_m4:
    st.metric(
        label="🚦 Backup Health Status",
        value=health_badge.split(" ")[1],
        delta=f"{status_counts['error']} Errors" if status_counts['error'] > 0 else "0 Errors",
        delta_color="normal" if status_counts['error'] == 0 else "inverse"
    )

st.markdown("---")

# ----------------- TABS INTERFACE ----------------- #
tab_calendar, tab_snapshots, tab_retention, tab_restore, tab_ec2, tab_dlm, tab_analytics, tab_iam = st.tabs([
    "🗓️ Physical Wall Calendar",
    "📸 Snapshot Inspector",
    "🧹 Retention & Purge",
    "🔄 Disaster Recovery & Restore",
    "🖥️ EC2 & EBS Setup",
    "☁️ AWS DLM Cloud Policy",
    "📊 Analytics & Report Export",
    "🛡️ IAM & LabRole Details"
])

# ----------------- TAB 1: VISUAL PHYSICAL WALL CALENDAR ----------------- #
with tab_calendar:
    st.subheader(f"🗓️ Physical Calendar Backup Grid — {today.strftime('%B %Y')}")
    st.markdown("Each day shows scheduled automated backup tiers aligned with real-world business calendar cycles:")
    st.markdown("🔵 **Daily (24h/7d)** &nbsp;&nbsp;|&nbsp;&nbsp; 🟣 **Weekly (Sundays/28d)** &nbsp;&nbsp;|&nbsp;&nbsp; 🟡 **Monthly (1st/365d)** &nbsp;&nbsp;|&nbsp;&nbsp; ❄️ **Blackout Freeze**")

    # Render 7-column calendar header
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cols_header = st.columns(7)
    for i, dow in enumerate(days_of_week):
        cols_header[i].markdown(f"**{dow}**")

    # Render month calendar grid
    month_grid = calendar_engine.get_month_calendar_matrix(today.year, today.month)
    for week in month_grid:
        cols_w = st.columns(7)
        for i, cell in enumerate(week):
            with cols_w[i]:
                if cell["day"] is None:
                    st.markdown("<div class='cal-day-cell' style='opacity:0.2;'></div>", unsafe_allow_html=True)
                else:
                    today_cls = "cal-today" if cell["is_today"] else ""
                    badges_html = ""
                    if cell["is_blackout"]:
                        badges_html += "<span class='badge-blackout'>❄️ Freeze</span>"
                    else:
                        for t in cell["tiers"]:
                            if t == "Daily": badges_html += "<span class='badge-daily'>Daily</span>"
                            elif t == "Weekly": badges_html += "<span class='badge-weekly'>Weekly</span>"
                            elif t == "Monthly": badges_html += "<span class='badge-monthly'>Monthly</span>"

                    today_tag = " <b style='color:#38ef7d;'>• Today</b>" if cell["is_today"] else ""
                    st.markdown(f"""
                    <div class='cal-day-cell {today_cls}'>
                        <div style='font-size:13px; font-weight:bold;'>{cell['day']}{today_tag}</div>
                        <div>{badges_html}</div>
                    </div>
                    """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("🚀 Trigger Today's Scheduled Calendar Backup")
    col_trig1, col_trig2 = st.columns([3, 1])
    with col_trig1:
        st.write(f"Today is **{today.strftime('%A, %B %d, %Y')}**. Scheduled Tiers: `{', '.join([t['tier'] for t in today_tiers]) or 'None'}`")
    with col_trig2:
        if st.button("🚀 Run Calendar Backup Now", type="primary", use_container_width=True):
            res = snapshot_manager.run_calendar_lifecycle(today)
            if res["status"] == "COMPLETED":
                st.toast(f"Created {len(res['created_snapshots'])} snapshots!")
                st.rerun()
            elif res["status"] == "SKIPPED_BLACKOUT":
                st.warning(f"Skipped due to change blackout freeze: {res['reason']}")
            else:
                st.info(f"Status: {res['status']}")

# ----------------- TAB 2: SNAPSHOT INSPECTOR ----------------- #
with tab_snapshots:
    st.subheader("📸 Managed EBS Snapshots Inspection")
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        st.markdown(f"Total Snapshots: **{len(snapshots_list)}** | Active: **{audit_info['active_count']}** | Expired: **{audit_info['expired_count']}** | Errors: **{status_counts['error']}**")
    with col_s2:
        if st.button("📸 Trigger Manual Snapshot", use_container_width=True):
            vols = snapshot_manager.list_volumes()
            target_vols = [v["VolumeId"] for v in vols if v["IsBackupTarget"]]
            if target_vols:
                res = snapshot_manager.create_calendar_snapshot(target_vols[0], "Daily")
                st.toast(f"Snapshot created: {res.get('SnapshotId')}")
                st.rerun()
            else:
                st.warning("Please tag at least one volume with Backup=Daily.")

    if snapshots_list:
        snap_rows = []
        for s in snapshots_list:
            state_val = s.get("State", "completed").capitalize()
            status_icon = "❌ Error" if "error" in state_val.lower() else ("⏳ Pending" if "pending" in state_val.lower() else "✅ Completed")
            retention_badge = "🔴 EXPIRED" if s["IsExpired"] else ("🟡 EXPIRING SOON" if s["DaysRemaining"] <= 1 else "🟢 ACTIVE")
            snap_rows.append({
                "Snapshot ID": s["SnapshotId"],
                "Volume ID": s["VolumeId"],
                "Size (GB)": s["VolumeSize"],
                "Tier": s["ScheduleTier"],
                "Calendar Date": s["CalendarDate"],
                "Expires On": s["ExpireOn"],
                "Days Left": s["DaysRemaining"],
                "Status": status_icon,
                "Retention Health": retention_badge
            })
        st.dataframe(pd.DataFrame(snap_rows), use_container_width=True)
    else:
        st.info("No snapshots found yet. Click 'Run Calendar Backup Now' or 'Auto-Repair'.")

# ----------------- TAB 3: RETENTION & PURGE ----------------- #
with tab_retention:
    st.subheader("🧹 Snapshot Retention Policies & Automatic Deletion")
    col_ret1, col_ret2, col_ret3 = st.columns(3)
    col_ret1.metric("Expired Snapshots Due for Purge", audit_info["expired_count"])
    col_ret2.metric("Storage to Reclaim", f"{audit_info['expired_total_gb']} GB")
    col_ret3.metric("Cost Reclaimable", f"${cost_metrics['reclaimable_savings_usd']} / mo")

    if audit_info["expired_count"] > 0:
        st.warning(f"⚠️ Found **{audit_info['expired_count']}** snapshot(s) that have passed their retention limit!")
        expired_table = [{
            "Snapshot ID": s["SnapshotId"],
            "Volume ID": s["VolumeId"],
            "Size (GB)": s["VolumeSize"],
            "Tier": s["ScheduleTier"],
            "Created Date": s["CalendarDate"],
            "Expired Date": s["ExpireOn"],
            "Days Overdue": abs(s["DaysRemaining"])
        } for s in audit_info["expired_snapshots"]]
        st.dataframe(pd.DataFrame(expired_table), use_container_width=True)

        col_pur1, col_pur2 = st.columns(2)
        with col_pur1:
            if st.button("🔍 Simulate Deletion (Dry-Run Audit)", use_container_width=True):
                res = snapshot_manager.purge_expired_snapshots(dry_run=True)
                st.info(f"[DRY-RUN] Would delete {res['purged_count']} snapshots and reclaim {res['reclaimed_gb']} GB.")
        with col_pur2:
            if st.button("🗑️ Automatically Delete Expired Snapshots Now", type="primary", use_container_width=True):
                res = snapshot_manager.purge_expired_snapshots(dry_run=False)
                st.toast(f"Purged {res['purged_count']} expired snapshots! Reclaimed {res['reclaimed_gb']} GB.")
                st.rerun()
    else:
        st.success("🎉 All snapshots are compliant with retention policies. Zero expired snapshots require deletion!")

# ----------------- TAB 4: DISASTER RECOVERY & RESTORATION ----------------- #
with tab_restore:
    st.subheader("🔄 Disaster Recovery (DR) & Volume Restoration")
    st.markdown("Test your backup restorability! Restore any snapshot into a brand new, fully functional Amazon EBS Volume.")

    dr_assessment = snapshot_manager.run_dr_assessment()
    col_dr1, col_dr2, col_dr3 = st.columns(3)
    col_dr1.metric("DR Readiness Score", f"{dr_assessment['dr_score']}%", delta="RPO Met" if dr_assessment['dr_score'] == 100 else "Action Required")
    col_dr2.metric("Volume Coverage", f"{dr_assessment['coverage_percentage']}%", f"{dr_assessment['protected_volumes']} of {dr_assessment['target_volumes']} Volumes")
    col_dr3.metric("RPO Status (<24h)", dr_assessment["rpo_status"])

    st.markdown("---")
    st.markdown("#### 🛠️ Restore Snapshot to New EBS Volume")
    if snapshots_list:
        col_res1, col_res2, col_res3 = st.columns([3, 2, 2])
        with col_res1:
            sel_snap = st.selectbox("Select Snapshot to Restore", [s["SnapshotId"] for s in snapshots_list])
        with col_res2:
            sel_az = st.selectbox("Target Availability Zone", ["us-east-1a", "us-east-1b", "us-east-1c"])
        with col_res3:
            st.write("")
            st.write("")
            if st.button("🔄 Restore to EBS Volume Now", type="primary", use_container_width=True):
                with st.spinner("Restoring volume from snapshot..."):
                    res = snapshot_manager.restore_volume_from_snapshot(sel_snap, sel_az)
                    if res.get("status") == "SUCCESS":
                        st.balloons()
                        st.success(f"✅ {res['message']} (New Volume ID: `{res['volume_id']}`)")
                    else:
                        st.error(res.get("message"))
    else:
        st.info("No snapshots available to restore.")

# ----------------- TAB 5: EC2 & EBS VOLUME SETUP ----------------- #
with tab_ec2:
    st.subheader("🖥️ EC2 Instances and Attached EBS Volumes")
    instances = ec2_manager.list_instances()
    if instances:
        inst_table = []
        for inst in instances:
            dev_str = ", ".join([f"{d['DeviceName']} ({d.get('VolumeId', 'N/A')})" for d in inst.get("BlockDevices", [])])
            inst_table.append({
                "Instance ID": inst["InstanceId"],
                "Name": inst["Name"],
                "State": inst["State"],
                "Type": inst["InstanceType"],
                "Attached Devices": dev_str,
                "Backup Tag": "✅ " + inst["Tags"].get("Backup", "None") if "Backup" in inst["Tags"] else "❌ Not Tagged"
            })
        st.dataframe(pd.DataFrame(inst_table), use_container_width=True)

        col_it1, col_it2 = st.columns([3, 1])
        with col_it1:
            sel_inst = st.selectbox("Select Instance to Tag", [i["InstanceId"] for i in instances])
        with col_it2:
            if st.button("Tag Instance & EBS Volumes", use_container_width=True):
                res = ec2_manager.tag_instance_and_volumes(sel_inst, "Backup", "Daily")
                if res.get("status") == "SUCCESS":
                    st.toast(f"Tagged {len(res['tagged_resources'])} resources!")
                    st.rerun()
    else:
        st.info("No EC2 instances found.")

# ----------------- TAB 6: DLM CLOUD POLICY ----------------- #
with tab_dlm:
    st.subheader("☁️ AWS Data Lifecycle Manager (DLM) Policy")
    st.markdown("Deploy cloud-native DLM policies to AWS using **`LabRole`**.")

    dlm_payload = dlm_manager.build_dlm_policy_payload()
    st.code(json.dumps(dlm_payload, indent=2), language="json")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        if st.button("🚀 Deploy DLM Policy to AWS Learner Lab", type="primary", use_container_width=True):
            res = dlm_manager.deploy_dlm_policy()
            if res.get("status") in ("DEPLOYED", "SIMULATED_SUCCESS"):
                st.toast("DLM Policy deployed!")
                st.success(f"✅ {res.get('message')} (Policy ID: `{res.get('policy_id')}`)")
            else:
                st.error(f"Error: {res.get('error')}")
    with col_d2:
        existing_policies = dlm_manager.list_existing_policies()
        st.write(f"Active DLM Policies: **{len(existing_policies)}**")

# ----------------- TAB 7: ANALYTICS & COMPLIANCE EXPORT ----------------- #
with tab_analytics:
    st.subheader("📊 Snapshot Storage Analytics & Compliance Report Exporter")
    col_an1, col_an2 = st.columns(2)
    with col_an1:
        st.markdown("#### 📈 Snapshots by Schedule Tier")
        tier_counts = {"Daily": 0, "Weekly": 0, "Monthly": 0, "Yearly": 0}
        for s in snapshots_list:
            t = s.get("ScheduleTier", "Daily")
            tier_counts[t] = tier_counts.get(t, 0) + 1
        st.bar_chart(pd.DataFrame(list(tier_counts.items()), columns=["Tier", "Count"]).set_index("Tier"))

    with col_an2:
        st.markdown("#### 💰 Cost Breakdown & Savings")
        st.metric("Total Monthly Snapshot Cost", f"${cost_metrics['monthly_cost_usd']}")
        st.metric("Potential Reclaimable Savings", f"${cost_metrics['reclaimable_savings_usd']}")
        st.caption("Pricing calculated at $0.05 per GB-month standard EBS snapshot rate.")

    st.markdown("---")
    st.subheader("📄 Download Formal Audit & Compliance Report")
    report_dict = {
        "report_generated_utc": datetime.utcnow().isoformat(),
        "health_status": health_status,
        "total_snapshots": len(snapshots_list),
        "active_snapshots": audit_info["active_count"],
        "expired_snapshots": audit_info["expired_count"],
        "total_storage_gb": cost_metrics["total_gb"],
        "monthly_estimated_bill_usd": cost_metrics["monthly_cost_usd"],
        "dr_readiness_score": dr_assessment["dr_score"],
        "snapshots": snapshots_list
    }
    report_json = json.dumps(report_dict, indent=2, default=str)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="📥 Download Audit Report (JSON)",
            data=report_json,
            file_name=f"snapshot_lifecycle_audit_{today}.json",
            mime="application/json",
            use_container_width=True
        )
    with col_dl2:
        if snapshots_list:
            df_export = pd.DataFrame(snapshots_list)
            csv_data = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Snapshots Inventory (CSV)",
                data=csv_data,
                file_name=f"ebs_snapshots_inventory_{today}.csv",
                mime="text/csv",
                use_container_width=True
            )

# ----------------- TAB 8: IAM & LABROLE DETAILS ----------------- #
with tab_iam:
    st.subheader("🛡️ IAM Roles & AWS Learner Lab Security Rules")
    role_info = iam_manager.inspect_lab_role()
    st.write(f"**Execution Role:** `{role_info['role_name']}`")
    st.write(f"**Role ARN:** `{role_info['role_arn']}`")
    st.write(f"**Compliance Status:** `{role_info['status']}`")

    st.info("""
    ### ⚠️ Crucial Rule for AWS Academy Learner Lab:
    * In AWS Academy / Educate Learner Labs, students are **restricted from creating new IAM roles** (`iam:CreateRole`).
    * If you select "Default role" in DLM, AWS tries to create `AWSDataLifecycleManagerDefaultRole` and fails with `AccessDenied`.
    * This project automatically uses the pre-authorized **`LabRole`** (`arn:aws:iam::<Account_ID>:role/LabRole`), which has full permissions for EC2, EBS, DLM, and CloudWatch.
    """)
