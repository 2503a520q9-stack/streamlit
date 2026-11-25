"""
Mock AWS Provider: Generates realistic mock data for EBS Volumes,
Snapshots, DLM Policies, and Volume Restoration for offline simulation.
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

class MockAWSProvider:
    def __init__(self):
        today = date.today()
        # Mock EBS Volumes
        self.volumes = [
            {
                "VolumeId": "vol-0a1b2c3d4e5f60001",
                "Size": 20,
                "State": "in-use",
                "VolumeType": "gp3",
                "AvailabilityZone": "us-east-1a",
                "CreateTime": datetime.now() - timedelta(days=60),
                "Attachments": [{"InstanceId": "i-01122334455667788", "Device": "/dev/xvda", "State": "attached"}],
                "Tags": [
                    {"Key": "Name", "Value": "WebServer-Root-Volume"},
                    {"Key": "Backup", "Value": "Daily"},
                    {"Key": "Environment", "Value": "Production"}
                ]
            },
            {
                "VolumeId": "vol-0a1b2c3d4e5f60002",
                "Size": 50,
                "State": "in-use",
                "VolumeType": "gp3",
                "AvailabilityZone": "us-east-1a",
                "CreateTime": datetime.now() - timedelta(days=45),
                "Attachments": [{"InstanceId": "i-01122334455667788", "Device": "/dev/xvdb", "State": "attached"}],
                "Tags": [
                    {"Key": "Name", "Value": "Database-Data-Volume"},
                    {"Key": "Backup", "Value": "Daily"},
                    {"Key": "Environment", "Value": "Production"}
                ]
            },
            {
                "VolumeId": "vol-0a1b2c3d4e5f60003",
                "Size": 10,
                "State": "available",
                "VolumeType": "gp2",
                "AvailabilityZone": "us-east-1b",
                "CreateTime": datetime.now() - timedelta(days=10),
                "Attachments": [],
                "Tags": [
                    {"Key": "Name", "Value": "Scratch-Temp-Volume"}
                ]
            }
        ]

        # Generate realistic mock snapshots spanning past dates (active and expired)
        self.snapshots = []
        vol_id = "vol-0a1b2c3d4e5f60001"

        # 1. Old expired daily snapshot (10 days old, retention was 7)
        d1 = today - timedelta(days=10)
        self.snapshots.append({
            "SnapshotId": "snap-0001dailyexpired",
            "VolumeId": vol_id,
            "VolumeSize": 20,
            "State": "completed",
            "StartTime": datetime.combine(d1, datetime.min.time()),
            "Description": f"Calendar Backup Daily - {vol_id} ({d1})",
            "Tags": [
                {"Key": "Name", "Value": f"Backup-{vol_id}-Daily-{d1}"},
                {"Key": "ScheduleTier", "Value": "Daily"},
                {"Key": "CalendarDate", "Value": d1.strftime("%Y-%m-%d")},
                {"Key": "ExpireOn", "Value": (d1 + timedelta(days=7)).strftime("%Y-%m-%d")},
                {"Key": "ManagedBy", "Value": "AWS-Snapshot-Lifecycle-Calendar"}
            ]
        })

        # 2. Active daily snapshots (past 3 days)
        for days_ago in [3, 2, 1]:
            d = today - timedelta(days=days_ago)
            self.snapshots.append({
                "SnapshotId": f"snap-0002daily{days_ago}ago",
                "VolumeId": vol_id,
                "VolumeSize": 20,
                "State": "completed",
                "StartTime": datetime.combine(d, datetime.min.time()),
                "Description": f"Calendar Backup Daily - {vol_id} ({d})",
                "Tags": [
                    {"Key": "Name", "Value": f"Backup-{vol_id}-Daily-{d}"},
                    {"Key": "ScheduleTier", "Value": "Daily"},
                    {"Key": "CalendarDate", "Value": d.strftime("%Y-%m-%d")},
                    {"Key": "ExpireOn", "Value": (d + timedelta(days=7)).strftime("%Y-%m-%d")},
                    {"Key": "ManagedBy", "Value": "AWS-Snapshot-Lifecycle-Calendar"}
                ]
            })

        # 3. Weekly snapshot (taken 2 weeks ago Sunday, retention 28 days -> ACTIVE)
        w_date = today - timedelta(days=14)
        self.snapshots.append({
            "SnapshotId": "snap-0003weeklyactive",
            "VolumeId": vol_id,
            "VolumeSize": 20,
            "State": "completed",
            "StartTime": datetime.combine(w_date, datetime.min.time()),
            "Description": f"Calendar Backup Weekly - {vol_id} ({w_date})",
            "Tags": [
                {"Key": "Name", "Value": f"Backup-{vol_id}-Weekly-{w_date}"},
                {"Key": "ScheduleTier", "Value": "Weekly"},
                {"Key": "CalendarDate", "Value": w_date.strftime("%Y-%m-%d")},
                {"Key": "ExpireOn", "Value": (w_date + timedelta(days=28)).strftime("%Y-%m-%d")},
                {"Key": "ManagedBy", "Value": "AWS-Snapshot-Lifecycle-Calendar"}
            ]
        })

        # 4. Expired weekly snapshot (taken 35 days ago, retention 28 -> EXPIRED)
        w_old = today - timedelta(days=35)
        self.snapshots.append({
            "SnapshotId": "snap-0004weeklyexpired",
            "VolumeId": vol_id,
            "VolumeSize": 20,
            "State": "completed",
            "StartTime": datetime.combine(w_old, datetime.min.time()),
            "Description": f"Calendar Backup Weekly - {vol_id} ({w_old})",
            "Tags": [
                {"Key": "Name", "Value": f"Backup-{vol_id}-Weekly-{w_old}"},
                {"Key": "ScheduleTier", "Value": "Weekly"},
                {"Key": "CalendarDate", "Value": w_old.strftime("%Y-%m-%d")},
                {"Key": "ExpireOn", "Value": (w_old + timedelta(days=28)).strftime("%Y-%m-%d")},
                {"Key": "ManagedBy", "Value": "AWS-Snapshot-Lifecycle-Calendar"}
            ]
        })

        # 5. Monthly snapshot (active, taken 1st of current month)
        m_date = today.replace(day=1)
        self.snapshots.append({
            "SnapshotId": "snap-0005monthlyactive",
            "VolumeId": vol_id,
            "VolumeSize": 20,
            "State": "completed",
            "StartTime": datetime.combine(m_date, datetime.min.time()),
            "Description": f"Calendar Backup Monthly - {vol_id} ({m_date})",
            "Tags": [
                {"Key": "Name", "Value": f"Backup-{vol_id}-Monthly-{m_date}"},
                {"Key": "ScheduleTier", "Value": "Monthly"},
                {"Key": "CalendarDate", "Value": m_date.strftime("%Y-%m-%d")},
                {"Key": "ExpireOn", "Value": (m_date + timedelta(days=365)).strftime("%Y-%m-%d")},
                {"Key": "ManagedBy", "Value": "AWS-Snapshot-Lifecycle-Calendar"}
            ]
        })

    def describe_volumes(self, **kwargs) -> Dict[str, Any]:
        return {"Volumes": self.volumes}

    def describe_snapshots(self, **kwargs) -> Dict[str, Any]:
        return {"Snapshots": self.snapshots}

    def create_snapshot(self, VolumeId: str, Description: str = "", TagSpecifications: List = None) -> Dict[str, Any]:
        new_id = f"snap-{len(self.snapshots) + 1:04d}simulated"
        tags = []
        if TagSpecifications:
            for spec in TagSpecifications:
                tags.extend(spec.get("Tags", []))

        vol = next((v for v in self.volumes if v["VolumeId"] == VolumeId), None)
        vol_size = vol["Size"] if vol else 20

        new_snap = {
            "SnapshotId": new_id,
            "VolumeId": VolumeId,
            "VolumeSize": vol_size,
            "State": "completed",
            "StartTime": datetime.now(),
            "Description": Description,
            "Tags": tags
        }
        self.snapshots.insert(0, new_snap)
        return new_snap

    def delete_snapshot(self, SnapshotId: str) -> None:
        self.snapshots = [s for s in self.snapshots if s["SnapshotId"] != SnapshotId]

    def create_tags(self, Resources: List[str], Tags: List[Dict[str, str]]) -> None:
        for res_id in Resources:
            for vol in self.volumes:
                if vol["VolumeId"] == res_id:
                    existing = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
                    for t in Tags:
                        existing[t["Key"]] = t["Value"]
                    vol["Tags"] = [{"Key": k, "Value": v} for k, v in existing.items()]

    def create_volume(self, SnapshotId: str, AvailabilityZone: str = "us-east-1a", VolumeType: str = "gp3", TagSpecifications: List = None) -> Dict[str, Any]:
        snap = next((s for s in self.snapshots if s["SnapshotId"] == SnapshotId), None)
        size = snap["VolumeSize"] if snap else 20
        new_vol_id = f"vol-restored-{len(self.volumes) + 1:04d}"
        tags = [{"Key": "Name", "Value": f"Restored-from-{SnapshotId}"}]
        if TagSpecifications:
            for spec in TagSpecifications:
                tags.extend(spec.get("Tags", []))

        new_vol = {
            "VolumeId": new_vol_id,
            "Size": size,
            "State": "available",
            "VolumeType": VolumeType,
            "AvailabilityZone": AvailabilityZone,
            "CreateTime": datetime.now(),
            "Attachments": [],
            "Tags": tags
        }
        self.volumes.append(new_vol)
        return new_vol
