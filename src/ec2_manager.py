"""
EC2 Manager: Manages EC2 instances, attached EBS volumes, and testing infrastructure in AWS Learner Lab.
"""
from typing import List, Dict, Any, Optional
from src.aws_client import AWSClientManager

class EC2Manager:
    def __init__(self, aws_client: AWSClientManager):
        self.aws = aws_client
        self.ec2 = aws_client.get_ec2_client()

    def list_instances(self) -> List[Dict[str, Any]]:
        """Lists EC2 instances with state, attached EBS volumes, and tags."""
        if self.aws.is_mock:
            return [
                {
                    "InstanceId": "i-01122334455667788",
                    "State": "running",
                    "InstanceType": "t2.micro",
                    "Name": "Production-WebServer-01",
                    "PublicIp": "54.210.45.12",
                    "PrivateIp": "172.31.10.5",
                    "BlockDevices": [
                        {"DeviceName": "/dev/xvda", "VolumeId": "vol-0a1b2c3d4e5f60001", "Size": 20},
                        {"DeviceName": "/dev/xvdb", "VolumeId": "vol-0a1b2c3d4e5f60002", "Size": 50}
                    ],
                    "Tags": {"Name": "Production-WebServer-01", "Environment": "Production", "Backup": "Daily"}
                }
            ]

        try:
            res = self.ec2.describe_instances()
            instances = []
            for resv in res.get("Reservations", []):
                for inst in resv.get("Instances", []):
                    tags = {t.get("Key"): t.get("Value") for t in inst.get("Tags", [])}
                    devices = []
                    for bdm in inst.get("BlockDeviceMapping", []):
                        ebs = bdm.get("Ebs", {})
                        devices.append({
                            "DeviceName": bdm.get("DeviceName"),
                            "VolumeId": ebs.get("VolumeId"),
                            "Status": ebs.get("Status")
                        })
                    instances.append({
                        "InstanceId": inst["InstanceId"],
                        "State": inst.get("State", {}).get("Name", "unknown"),
                        "InstanceType": inst.get("InstanceType", "t2.micro"),
                        "Name": tags.get("Name", inst["InstanceId"]),
                        "PublicIp": inst.get("PublicIpAddress", "N/A"),
                        "PrivateIp": inst.get("PrivateIpAddress", "N/A"),
                        "BlockDevices": devices,
                        "Tags": tags
                    })
            return instances
        except Exception as e:
            print(f"Error listing EC2 instances: {e}")
            return []

    def tag_instance_and_volumes(self, instance_id: str, tag_key: str = "Backup", tag_value: str = "Daily") -> Dict[str, Any]:
        """Tags an EC2 instance and all attached EBS volumes for calendar lifecycle backup."""
        instances = self.list_instances()
        target = next((i for i in instances if i["InstanceId"] == instance_id), None)
        if not target:
            return {"status": "ERROR", "message": f"Instance {instance_id} not found."}

        resources = [instance_id]
        for dev in target.get("BlockDevices", []):
            if "VolumeId" in dev and dev["VolumeId"]:
                resources.append(dev["VolumeId"])

        try:
            self.ec2.create_tags(
                Resources=resources,
                Tags=[{"Key": tag_key, "Value": tag_value}]
            )
            return {
                "status": "SUCCESS",
                "tagged_resources": resources,
                "tag": f"{tag_key}={tag_value}"
            }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
