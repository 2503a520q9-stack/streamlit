"""
Snapshot Manager: Orchestrates snapshot creation, metadata tagging,
retention audits, lifecycle purging, volume restoration, and DR compliance audits.
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from src.aws_client import AWSClientManager
from src.calendar_engine import CalendarEngine

MANAGED_TAG = "AWS-Snapshot-Lifecycle-Calendar"

class SnapshotManager:
    def __init__(self, aws_client: AWSClientManager, calendar_engine: CalendarEngine, policy_config: Dict[str, Any]):
        self.aws = aws_client
        self.ec2 = aws_client.get_ec2_client()
        self.calendar = calendar_engine
        self.policy = policy_config
        self.target_tags = policy_config.get("target_tags", {"Backup": "Daily"})

    def list_volumes(self) -> List[Dict[str, Any]]:
        """Lists all EBS volumes in region with attachment and backup readiness info."""
        response = self.ec2.describe_volumes()
        volumes = response.get("Volumes", [])
        formatted = []
        for v in volumes:
            tags = {t["Key"]: t["Value"] for t in v.get("Tags", [])}
            is_target = all(tags.get(k) == v for k, v in self.target_tags.items())

            attachments = v.get("Attachments", [])
            instance_id = attachments[0]["InstanceId"] if attachments else "Unattached"
            device = attachments[0]["Device"] if attachments else "N/A"

            formatted.append({
                "VolumeId": v["VolumeId"],
                "Size": v["Size"],
                "State": v["State"],
                "VolumeType": v.get("VolumeType", "gp3"),
                "AvailabilityZone": v.get("AvailabilityZone", "N/A"),
                "InstanceId": instance_id,
                "Device": device,
                "Tags": tags,
                "Name": tags.get("Name", v["VolumeId"]),
                "IsBackupTarget": is_target
            })
        return formatted

    def tag_volume_for_backup(self, volume_id: str, tag_key: str = "Backup", tag_value: str = "Daily") -> None:
        """Applies target backup tag to an EBS volume."""
        self.ec2.create_tags(
            Resources=[volume_id],
            Tags=[{"Key": tag_key, "Value": tag_value}]
        )

    def create_calendar_snapshot(self, volume_id: str, tier: str = "Daily", custom_date: Optional[date] = None) -> Dict[str, Any]:
        """Creates an EBS snapshot with physical calendar metadata tags."""
        snap_date = custom_date or date.today()
        date_str = snap_date.strftime("%Y-%m-%d")

        tier_cfg = self.policy.get("schedules", {}).get(tier.lower(), {})
        retention_days = tier_cfg.get("retention_days", 7)
        expire_date = self.calendar.calculate_expiration_date(snap_date, retention_days)
        expire_str = expire_date.strftime("%Y-%m-%d")

        description = f"Physical Calendar {tier} Backup for {volume_id} on {date_str} (Expires {expire_str})"
        tags = [
            {"Key": "Name", "Value": f"Backup-{volume_id}-{tier}-{date_str}"},
            {"Key": "ScheduleTier", "Value": tier},
            {"Key": "CalendarDate", "Value": date_str},
            {"Key": "ExpireOn", "Value": expire_str},
            {"Key": "ManagedBy", "Value": MANAGED_TAG}
        ]

        result = self.ec2.create_snapshot(
            VolumeId=volume_id,
            Description=description,
            TagSpecifications=[{
                "ResourceType": "snapshot",
                "Tags": tags
            }]
        )
        return result

    def list_managed_snapshots(self) -> List[Dict[str, Any]]:
        """Lists snapshots managed by this calendar policy, enriched with metadata."""
        try:
            response = self.ec2.describe_snapshots(
                Filters=[{"Name": "tag:ManagedBy", "Values": [MANAGED_TAG]}]
            )
            raw = response.get("Snapshots", [])
        except Exception:
            response = self.ec2.describe_snapshots()
            raw = [s for s in response.get("Snapshots", [])
                   if any(t.get("Key") == "ManagedBy" and t.get("Value") == MANAGED_TAG for t in s.get("Tags", []))]

        today = date.today()
        snapshots = []
        for s in raw:
            audit = self.calendar.is_snapshot_expired(s, today)
            tags = {t.get("Key", ""): t.get("Value", "") for t in s.get("Tags", [])}

            snapshots.append({
                "SnapshotId": s.get("SnapshotId"),
                "VolumeId": s.get("VolumeId"),
                "VolumeSize": s.get("VolumeSize", 0),
                "State": s.get("State", "completed"),
                "StartTime": s.get("StartTime"),
                "Description": s.get("Description", ""),
                "Name": tags.get("Name", s.get("SnapshotId")),
                "ScheduleTier": tags.get("ScheduleTier", "Daily"),
                "CalendarDate": audit["created_date"],
                "ExpireOn": audit["expire_date"],
                "IsExpired": audit["is_expired"],
                "DaysRemaining": audit["days_remaining"],
                "LifecycleStatus": audit["status"]
            })

        snapshots.sort(key=lambda x: str(x["StartTime"]), reverse=True)
        return snapshots

    def run_calendar_lifecycle(self, check_date: Optional[date] = None) -> Dict[str, Any]:
        """Executes physical calendar backup cycle for the given date."""
        target_date = check_date or date.today()
        date_str = target_date.strftime("%Y-%m-%d")

        blackout = self.calendar.is_blackout(target_date)
        if blackout:
            return {
                "date": date_str,
                "status": "SKIPPED_BLACKOUT",
                "reason": blackout,
                "created_snapshots": []
            }

        applicable_tiers = self.calendar.get_applicable_tiers_for_date(target_date)
        if not applicable_tiers:
            return {
                "date": date_str,
                "status": "NO_SCHEDULES_DUE",
                "reason": "No calendar schedules configured to trigger on this date.",
                "created_snapshots": []
            }

        volumes = self.list_volumes()
        target_vols = [v for v in volumes if v["IsBackupTarget"]]

        created = []
        for vol in target_vols:
            for tier_info in applicable_tiers:
                tier_name = tier_info["tier"]
                res = self.create_calendar_snapshot(vol["VolumeId"], tier_name, target_date)
                created.append({
                    "SnapshotId": res.get("SnapshotId"),
                    "VolumeId": vol["VolumeId"],
                    "Tier": tier_name,
                    "Size": vol["Size"]
                })

        return {
            "date": date_str,
            "status": "COMPLETED",
            "active_tiers": [t["tier"] for t in applicable_tiers],
            "target_volumes_count": len(target_vols),
            "created_snapshots": created
        }

    def audit_retention(self, check_date: Optional[date] = None) -> Dict[str, Any]:
        """Audits all managed snapshots to find expired ones based on calendar rules."""
        curr_date = check_date or date.today()
        snapshots = self.list_managed_snapshots()

        expired = []
        active = []
        expiring_soon = []

        for s in snapshots:
            if s["IsExpired"]:
                expired.append(s)
            elif s["DaysRemaining"] <= 1:
                expiring_soon.append(s)
            else:
                active.append(s)

        total_expired_gb = sum(s["VolumeSize"] for s in expired)

        return {
            "check_date": curr_date.strftime("%Y-%m-%d"),
            "total_managed": len(snapshots),
            "active_count": len(active),
            "expiring_soon_count": len(expiring_soon),
            "expired_count": len(expired),
            "expired_total_gb": total_expired_gb,
            "expired_snapshots": expired
        }

    def purge_expired_snapshots(self, dry_run: bool = True, check_date: Optional[date] = None) -> Dict[str, Any]:
        """Deletes expired snapshots according to calendar rules."""
        audit = self.audit_retention(check_date)
        expired = audit["expired_snapshots"]

        purged_ids = []
        reclaimed_gb = 0

        for snap in expired:
            snap_id = snap["SnapshotId"]
            if not dry_run:
                try:
                    self.ec2.delete_snapshot(SnapshotId=snap_id)
                    purged_ids.append(snap_id)
                    reclaimed_gb += snap["VolumeSize"]
                except Exception as e:
                    print(f"Error deleting snapshot {snap_id}: {e}")
            else:
                purged_ids.append(snap_id)
                reclaimed_gb += snap["VolumeSize"]

        return {
            "dry_run": dry_run,
            "expired_count": len(expired),
            "purged_count": len(purged_ids),
            "purged_snapshot_ids": purged_ids,
            "reclaimed_gb": reclaimed_gb
        }

    def restore_volume_from_snapshot(self, snapshot_id: str, availability_zone: str = "us-east-1a", volume_type: str = "gp3") -> Dict[str, Any]:
        """
        Disaster Recovery Feature: Restores an EBS volume from any snapshot.
        Essential for testing backup restorability in AWS!
        """
        try:
            res = self.ec2.create_volume(
                SnapshotId=snapshot_id,
                AvailabilityZone=availability_zone,
                VolumeType=volume_type,
                TagSpecifications=[{
                    "ResourceType": "volume",
                    "Tags": [
                        {"Key": "Name", "Value": f"Restored-from-{snapshot_id}"},
                        {"Key": "RestoredFrom", "Value": snapshot_id},
                        {"Key": "RestoredAt", "Value": datetime.now().isoformat()}
                    ]
                }]
            )
            return {
                "status": "SUCCESS",
                "volume_id": res.get("VolumeId"),
                "size": res.get("Size"),
                "availability_zone": res.get("AvailabilityZone"),
                "message": f"Successfully created new EBS volume from snapshot {snapshot_id}!"
            }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def run_dr_assessment(self) -> Dict[str, Any]:
        """
        Evaluates Disaster Recovery (DR) Readiness:
        - Are all target volumes protected with at least one recent snapshot (< 24h)?
        - What is the Recovery Point Objective (RPO) status?
        """
        volumes = self.list_volumes()
        target_vols = [v for v in volumes if v["IsBackupTarget"]]
        snapshots = self.list_managed_snapshots()

        covered_vols = set()
        now = datetime.now()
        rpo_compliant = 0

        for s in snapshots:
            vol_id = s["VolumeId"]
            covered_vols.add(vol_id)
            # Check if taken within 24 hours
            try:
                st = s["StartTime"]
                if isinstance(st, str):
                    st = datetime.fromisoformat(st)
                # Naive comparison
                st_naive = st.replace(tzinfo=None) if hasattr(st, "tzinfo") and st.tzinfo else st
                if (now - st_naive).total_seconds() <= 86400:
                    rpo_compliant += 1
            except Exception:
                pass

        total_targets = len(target_vols) if target_vols else 1
        coverage_pct = round((len(covered_vols.intersection(set(v["VolumeId"] for v in target_vols))) / total_targets) * 100, 1)

        dr_score = 100 if coverage_pct == 100 and len(snapshots) > 0 else (50 if len(snapshots) > 0 else 0)

        return {
            "dr_score": dr_score,
            "target_volumes": len(target_vols),
            "protected_volumes": len(covered_vols),
            "coverage_percentage": coverage_pct,
            "rpo_status": "EXCELLENT (< 24h)" if rpo_compliant > 0 else "BACKUP DUE",
            "total_snapshots": len(snapshots)
        }
