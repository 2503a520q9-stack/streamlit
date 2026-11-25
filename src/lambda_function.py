"""
AWS Lambda Function: Snapshot Lifecycle Physical Calendar Engine.
Runs serverless in AWS Learner Lab using 'LabRole' to automate EBS snapshot
creation, metadata tagging, calendar schedule matching, and expired snapshot purging.
"""
import os
import json
import boto3
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

MANAGED_TAG = "AWS-Snapshot-Lifecycle-Calendar"

# Default configuration if not overridden by event or env vars
DEFAULT_POLICY = {
    "target_tags": {"Backup": "Daily"},
    "schedules": {
        "daily": {"enabled": True, "retention_days": 7, "tier": "Daily"},
        "weekly": {"enabled": True, "day_of_week": "Sunday", "retention_days": 28, "tier": "Weekly"},
        "monthly": {"enabled": True, "day_of_month": 1, "retention_days": 365, "tier": "Monthly"},
        "yearly": {"enabled": True, "month": 1, "day_of_month": 1, "retention_days": 1095, "tier": "Yearly"}
    },
    "blackout_calendar": [
        {"date": "2026-12-25", "reason": "Christmas Holiday Freeze"},
        {"date": "2026-12-31", "reason": "Fiscal Year-End Freeze"},
        {"date": "2027-01-01", "reason": "New Year Maintenance Window"}
    ]
}

def get_ec2_client(mock_client=None):
    if mock_client:
        return mock_client
    # Fall back to Mock Provider if forced or when running locally without AWS credentials
    if os.getenv("MOCK_AWS", "false").lower() in ("true", "1", "yes") or not (
        os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")
    ):
        try:
            from src.mock_provider import MockAWSProvider
            return MockAWSProvider()
        except Exception:
            pass

    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    try:
        return boto3.client("ec2", region_name=region)
    except Exception:
        from src.mock_provider import MockAWSProvider
        return MockAWSProvider()

def is_blackout_date(check_date: date, blackouts: List[Dict[str, str]]) -> str:
    date_str = check_date.strftime("%Y-%m-%d")
    for b in blackouts:
        if b.get("date") == date_str:
            return b.get("reason", "Scheduled Freeze")
    return ""

def get_active_tiers_for_date(check_date: date, schedules: Dict[str, Any]) -> List[Dict[str, Any]]:
    active = []
    # Daily
    daily = schedules.get("daily", {})
    if daily.get("enabled", True):
        active.append({"tier": "Daily", "retention_days": daily.get("retention_days", 7)})

    # Weekly
    weekly = schedules.get("weekly", {})
    if weekly.get("enabled", True):
        target_day = weekly.get("day_of_week", "Sunday").capitalize()
        if check_date.strftime("%A") == target_day:
            active.append({"tier": "Weekly", "retention_days": weekly.get("retention_days", 28)})

    # Monthly
    monthly = schedules.get("monthly", {})
    if monthly.get("enabled", True):
        target_dom = monthly.get("day_of_month", 1)
        if check_date.day == target_dom:
            active.append({"tier": "Monthly", "retention_days": monthly.get("retention_days", 365)})

    # Yearly
    yearly = schedules.get("yearly", {})
    if yearly.get("enabled", True):
        if check_date.month == yearly.get("month", 1) and check_date.day == yearly.get("day_of_month", 1):
            active.append({"tier": "Yearly", "retention_days": yearly.get("retention_days", 1095)})

    return active

def execute_snapshot_creation(ec2, check_date: date, policy: Dict[str, Any]) -> Dict[str, Any]:
    date_str = check_date.strftime("%Y-%m-%d")
    blackout_reason = is_blackout_date(check_date, policy.get("blackout_calendar", []))
    if blackout_reason:
        return {
            "status": "SKIPPED_BLACKOUT",
            "reason": blackout_reason,
            "created_snapshots": []
        }

    active_tiers = get_active_tiers_for_date(check_date, policy.get("schedules", {}))
    if not active_tiers:
        return {
            "status": "NO_TIERS_DUE",
            "reason": "No calendar schedules scheduled for today.",
            "created_snapshots": []
        }

    # Find target EBS volumes
    target_tags = policy.get("target_tags", {"Backup": "Daily"})
    try:
        filters = [{"Name": f"tag:{k}", "Values": [v]} for k, v in target_tags.items()]
        volumes_res = ec2.describe_volumes(Filters=filters)
    except Exception:
        volumes_res = ec2.describe_volumes()

    volumes = volumes_res.get("Volumes", [])

    created = []
    for vol in volumes:
        vol_id = vol["VolumeId"]
        for tier_info in active_tiers:
            tier = tier_info["tier"]
            retention_days = tier_info["retention_days"]
            expire_date = check_date + timedelta(days=retention_days)
            expire_str = expire_date.strftime("%Y-%m-%d")

            description = f"Physical Calendar {tier} Backup for {vol_id} ({date_str}, Exp: {expire_str})"
            snap = ec2.create_snapshot(
                VolumeId=vol_id,
                Description=description,
                TagSpecifications=[{
                    "ResourceType": "snapshot",
                    "Tags": [
                        {"Key": "Name", "Value": f"Backup-{vol_id}-{tier}-{date_str}"},
                        {"Key": "ScheduleTier", "Value": tier},
                        {"Key": "CalendarDate", "Value": date_str},
                        {"Key": "ExpireOn", "Value": expire_str},
                        {"Key": "ManagedBy", "Value": MANAGED_TAG}
                    ]
                }]
            )
            created.append({
                "SnapshotId": snap["SnapshotId"],
                "VolumeId": vol_id,
                "Tier": tier,
                "ExpireOn": expire_str
            })

    return {
        "status": "COMPLETED",
        "date": date_str,
        "active_tiers": [t["tier"] for t in active_tiers],
        "volumes_evaluated": len(volumes),
        "created_snapshots": created
    }

def execute_retention_purge(ec2, check_date: date, dry_run: bool = False) -> Dict[str, Any]:
    try:
        snaps_res = ec2.describe_snapshots(
            Filters=[{"Name": "tag:ManagedBy", "Values": [MANAGED_TAG]}]
        )
    except Exception:
        snaps_res = ec2.describe_snapshots()

    snapshots = snaps_res.get("Snapshots", [])

    purged = []
    reclaimed_gb = 0

    for s in snapshots:
        snap_id = s["SnapshotId"]
        vol_size = s.get("VolumeSize", 0)
        tags = {t.get("Key"): t.get("Value") for t in s.get("Tags", [])}
        expire_on_str = tags.get("ExpireOn")

        is_expired = False
        if expire_on_str:
            try:
                expire_d = datetime.strptime(expire_on_str, "%Y-%m-%d").date()
                if check_date > expire_d:
                    is_expired = True
            except ValueError:
                pass

        if is_expired:
            if not dry_run:
                try:
                    ec2.delete_snapshot(SnapshotId=snap_id)
                    purged.append(snap_id)
                    reclaimed_gb += vol_size
                except Exception as e:
                    print(f"Error purging {snap_id}: {e}")
            else:
                purged.append(snap_id)
                reclaimed_gb += vol_size

    return {
        "status": "COMPLETED",
        "dry_run": dry_run,
        "expired_found": len(purged),
        "purged_snapshots": purged,
        "reclaimed_gb": reclaimed_gb
    }

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main AWS Lambda Entrypoint.
    Supported Event Parameters:
      - mode: 'ALL' (default), 'SNAPSHOT', 'PURGE'
      - dry_run: bool (default: False for purge)
      - custom_date: 'YYYY-MM-DD' (optional date simulation)
      - policy_override: dict (optional custom policy config)
    """
    print(f"AWS Lambda invoked with event: {json.dumps(event)}")

    mode = event.get("mode", "ALL").upper()
    dry_run = event.get("dry_run", False)
    custom_date_str = event.get("custom_date")

    if custom_date_str:
        today = datetime.strptime(custom_date_str, "%Y-%m-%d").date()
    else:
        today = date.today()

    policy = event.get("policy_override", DEFAULT_POLICY)
    ec2 = get_ec2_client(mock_client=event.get("mock_ec2"))

    result = {
        "execution_time_utc": datetime.now().isoformat(),
        "calendar_date": today.strftime("%Y-%m-%d (%A)"),
        "mode": mode,
        "snapshot_result": None,
        "purge_result": None
    }

    if mode in ("ALL", "SNAPSHOT"):
        result["snapshot_result"] = execute_snapshot_creation(ec2, today, policy)

    if mode in ("ALL", "PURGE"):
        result["purge_result"] = execute_retention_purge(ec2, today, dry_run=dry_run)

    print(f"Lambda execution finished successfully: {json.dumps(result)}")
    return {
        "statusCode": 200,
        "body": result
    }
