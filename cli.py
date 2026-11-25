"""
Command Line Interface: AWS Snapshot Lifecycle Physical Calendar
Execute and automate calendar lifecycle tasks directly from VS Code Terminal.
"""
import sys
import argparse
from datetime import datetime, date
import json

from config.settings import load_policy_config
from src.aws_client import AWSClientManager
from src.calendar_engine import CalendarEngine
from src.snapshot_manager import SnapshotManager
from src.cost_guard import CostGuard
from src.dlm_manager import DLMManager

def print_header(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(
        description="AWS Snapshot Lifecycle Physical Calendar CLI (AWS Learner Lab Ready)"
    )
    parser.add_argument("--mock", action="store_true", help="Force mock mode (no AWS credentials required)")
    parser.add_argument("--region", default="us-east-1", help="AWS Region (default: us-east-1)")

    subparsers = parser.add_subparsers(dest="command", help="Available Commands")

    # Command: status
    subparsers.add_parser("status", help="Display EBS volumes, managed snapshots, and Learner Lab budget status")

    # Command: forecast
    p_fc = subparsers.add_parser("forecast", help="Display physical calendar backup schedule forecast")
    p_fc.add_argument("--days", type=int, default=14, help="Days ahead to forecast (default: 14)")

    # Command: run-schedule
    p_run = subparsers.add_parser("run-schedule", help="Execute physical calendar backup cycle for a given date")
    p_run.add_argument("--date", help="Target calendar date (YYYY-MM-DD). Defaults to today.")

    # Command: audit
    p_aud = subparsers.add_parser("audit", help="Audit managed snapshots against physical calendar retention rules")
    p_aud.add_argument("--date", help="Check date (YYYY-MM-DD). Defaults to today.")

    # Command: purge
    p_purge = subparsers.add_parser("purge", help="Delete expired snapshots past their physical calendar expiration")
    p_purge.add_argument("--dry-run", action="store_true", default=False, help="Simulate deletion without making changes")
    p_purge.add_argument("--force", action="store_true", default=False, help="Execute actual deletion")

    # Command: restore
    p_res = subparsers.add_parser("restore", help="Disaster Recovery: Restore an EBS volume from any snapshot")
    p_res.add_argument("snapshot_id", help="EBS Snapshot ID (e.g. snap-0123456789)")
    p_res.add_argument("--az", default="us-east-1a", help="Availability Zone (default: us-east-1a)")

    # Command: dr-assessment
    subparsers.add_parser("dr-assessment", help="Evaluate Disaster Recovery (DR) Readiness score and RPO compliance")

    # Command: tag-volume
    p_tag = subparsers.add_parser("tag-volume", help="Tag an EBS volume for calendar backup")
    p_tag.add_argument("volume_id", help="EBS Volume ID (e.g. vol-0123456789)")
    p_tag.add_argument("--key", default="Backup", help="Tag Key (default: Backup)")
    p_tag.add_argument("--value", default="Daily", help="Tag Value (default: Daily)")

    # Command: deploy-dlm
    subparsers.add_parser("deploy-dlm", help="Deploy native AWS Data Lifecycle Manager policy configured with LabRole")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Initialize components
    policy = load_policy_config()
    aws = AWSClientManager(region=args.region, force_mock=args.mock)
    cal = CalendarEngine(policy)
    sm = SnapshotManager(aws, cal, policy)
    guard = CostGuard(
        total_budget_usd=policy.get("budget_guard", {}).get("learner_lab_total_budget_usd", 100.0),
        ebs_cost_per_gb_month=policy.get("budget_guard", {}).get("ebs_cost_per_gb_month", 0.05),
        alert_threshold_usd=policy.get("budget_guard", {}).get("alert_threshold_usd", 5.0)
    )
    dlm = DLMManager(aws, policy)

    conn = aws.get_connection_info()

    # ---------------- STATUS ---------------- #
    if args.command == "status":
        print_header("AWS SNAPSHOT LIFECYCLE PHYSICAL CALENDAR - STATUS")
        print(f"AWS Environment : {'[SIMULATOR / MOCK]' if conn['is_mock'] else '[LIVE AWS LEARNER LAB]'}")
        print(f"Account ID      : {conn['account_id']}")
        print(f"Learner Role    : {conn['lab_role_arn']}")
        print(f"Region          : {conn['region']}")

        volumes = sm.list_volumes()
        print(f"\n[EBS Volumes: {len(volumes)}]")
        for v in volumes:
            mark = "[TARGET]" if v["IsBackupTarget"] else "[SKIP]  "
            print(f"  {mark} {v['VolumeId']} | {v['Size']:>3} GB | State: {v['State']:<10} | Instance: {v['InstanceId']} | Name: {v['Name']}")

        snaps = sm.list_managed_snapshots()
        audit = sm.audit_retention()
        cost = guard.calculate_snapshot_costs(snaps, audit["expired_count"], audit["expired_total_gb"])

        print(f"\n[Managed Snapshots: {len(snaps)}]")
        print(f"  - Active: {audit['active_count']}  |  Expiring Soon: {audit['expiring_soon_count']}  |  Expired: {audit['expired_count']}")
        print(f"\n[Learner Lab Budget Guard ($100 Lab Limit)]")
        print(f"  - Total Snapshot Storage : {cost['total_gb']} GB")
        print(f"  - Estimated Monthly Cost : ${cost['monthly_cost_usd']:.2f} / month")
        print(f"  - Lab Budget Utilization : {cost['budget_used_percentage']}% of $100")
        if cost["reclaimable_savings_usd"] > 0:
            print(f"  - Reclaimable Savings    : ${cost['reclaimable_savings_usd']:.2f}/mo (by purging {audit['expired_count']} expired snapshots)")

    # ---------------- FORECAST ---------------- #
    elif args.command == "forecast":
        print_header(f"PHYSICAL CALENDAR SCHEDULE FORECAST (Next {args.days} Days)")
        today = date.today()
        projections = cal.generate_projection(today, days_ahead=args.days)
        print(f"{'Date':<12} | {'Day':<10} | {'Status':<16} | {'Tiers Triggered':<20} | {'Blackout'}")
        print("-" * 75)
        for p in projections:
            tiers = ", ".join(p["scheduled_tiers"]) if p["scheduled_tiers"] else "—"
            st_str = "BLACKOUT" if p["is_blackout"] else ("SCHEDULED" if p["scheduled_tiers"] else "Idle")
            reason = p["blackout_reason"] or ""
            print(f"{p['date']:<12} | {p['day_name']:<10} | {st_str:<16} | {tiers:<20} | {reason}")

    # ---------------- RUN-SCHEDULE ---------------- #
    elif args.command == "run-schedule":
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        print_header(f"RUNNING CALENDAR BACKUP CYCLE - {target_date.strftime('%Y-%m-%d (%A)')}")
        res = sm.run_calendar_lifecycle(target_date)
        print(f"Result Status: {res['status']}")
        if res["status"] == "COMPLETED":
            print(f"Active Tiers Triggered: {', '.join(res['active_tiers'])}")
            print(f"Target Volumes Count  : {res['target_volumes_count']}")
            print("\nCreated Snapshots:")
            for s in res["created_snapshots"]:
                print(f"  + {s['SnapshotId']} | Volume: {s['VolumeId']} | Tier: {s['Tier']} ({s['Size']} GB)")
        elif res["status"] == "SKIPPED_BLACKOUT":
            print(f"Execution Skipped: Blackout Window ({res['reason']})")
        else:
            print(f"Details: {res.get('reason')}")

    # ---------------- AUDIT ---------------- #
    elif args.command == "audit":
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        print_header(f"PHYSICAL CALENDAR RETENTION AUDIT (Date: {target_date})")
        audit = sm.audit_retention(target_date)
        print(f"Total Managed Snapshots : {audit['total_managed']}")
        print(f"Compliant / Active      : {audit['active_count']}")
        print(f"Expiring Soon (<= 1 day): {audit['expiring_soon_count']}")
        print(f"Expired Overdue         : {audit['expired_count']} ({audit['expired_total_gb']} GB)")

        if audit["expired_snapshots"]:
            print("\nExpired Snapshots Detail:")
            for s in audit["expired_snapshots"]:
                print(f"  - {s['SnapshotId']} | Vol: {s['VolumeId']} | Tier: {s['ScheduleTier']} | Expired: {s['ExpireOn']} ({abs(s['DaysRemaining'])} days overdue)")
            print("\nRun 'python cli.py purge --dry-run' to preview deletion, or '--force' to purge.")

    # ---------------- PURGE ---------------- #
    elif args.command == "purge":
        if not args.force and not args.dry_run:
            print("Please specify either --dry-run or --force.")
            sys.exit(1)

        is_dry = not args.force
        mode_str = "[DRY-RUN SIMULATION]" if is_dry else "[LIVE PURGE]"
        print_header(f"PURGING EXPIRED SNAPSHOTS {mode_str}")
        res = sm.purge_expired_snapshots(dry_run=is_dry)
        print(f"Expired Snapshots Found : {res['expired_count']}")
        print(f"Snapshots Purged        : {res['purged_count']}")
        print(f"Storage Reclaimed       : {res['reclaimed_gb']} GB")
        if res["purged_snapshot_ids"]:
            print("\nPurged Snapshot IDs:")
            for sid in res["purged_snapshot_ids"]:
                print(f"  x {sid}")

    # ---------------- RESTORE ---------------- #
    elif args.command == "restore":
        print_header(f"DISASTER RECOVERY: RESTORING VOLUME FROM {args.snapshot_id}")
        res = sm.restore_volume_from_snapshot(args.snapshot_id, args.az)
        print(f"Status          : {res.get('status')}")
        print(f"New Volume ID   : {res.get('volume_id', 'N/A')}")
        print(f"Message         : {res.get('message')}")

    # ---------------- DR-ASSESSMENT ---------------- #
    elif args.command == "dr-assessment":
        print_header("DISASTER RECOVERY READINESS ASSESSMENT")
        dr = sm.run_dr_assessment()
        print(f"DR Readiness Score    : {dr['dr_score']}%")
        print(f"Volume Coverage       : {dr['coverage_percentage']}% ({dr['protected_volumes']}/{dr['target_volumes']} Volumes)")
        print(f"RPO Status (< 24h)    : {dr['rpo_status']}")
        print(f"Total Snapshots       : {dr['total_snapshots']}")

    # ---------------- TAG-VOLUME ---------------- #
    elif args.command == "tag-volume":
        print_header(f"TAGGING EBS VOLUME: {args.volume_id}")
        sm.tag_volume_for_backup(args.volume_id, args.key, args.value)
        print(f"Successfully applied tag: '{args.key}'='{args.value}' to {args.volume_id}")

    # ---------------- DEPLOY-DLM ---------------- #
    elif args.command == "deploy-dlm":
        print_header("DEPLOYING AWS DATA LIFECYCLE MANAGER (DLM) POLICY")
        print(f"Target IAM Role : {aws.get_lab_role_arn(dlm.lab_role_name)}")
        res = dlm.deploy_dlm_policy()
        print(f"Status          : {res.get('status')}")
        print(f"Policy ID       : {res.get('policy_id', 'N/A')}")
        print(f"Message         : {res.get('message', res.get('error'))}")

if __name__ == "__main__":
    main()
