"""
AWS Data Lifecycle Manager (DLM) Policy Automator:
Automates creation and management of native AWS DLM policies configured
with the mandatory 'LabRole' for AWS Learner Lab accounts.
"""
from typing import Dict, Any, List, Optional
from src.aws_client import AWSClientManager

class DLMManager:
    def __init__(self, aws_client: AWSClientManager, policy_config: Dict[str, Any]):
        self.aws = aws_client
        self.dlm = aws_client.get_dlm_client()
        self.policy_config = policy_config
        self.lab_role_name = policy_config.get("learner_lab", {}).get("iam_role_name", "LabRole")

    def build_dlm_policy_payload(self) -> Dict[str, Any]:
        """Constructs the native DLM policy specification matching our calendar rules."""
        role_arn = self.aws.get_lab_role_arn(self.lab_role_name)
        target_tags = self.policy_config.get("target_tags", {"Backup": "Daily"})

        target_tags_list = [{"Key": k, "Value": v} for k, v in target_tags.items()]

        schedules = self.policy_config.get("schedules", {})
        daily_cfg = schedules.get("daily", {})
        weekly_cfg = schedules.get("weekly", {})
        monthly_cfg = schedules.get("monthly", {})

        dlm_schedules = []

        # 1. Daily Schedule (runs every 24h at specified UTC hour)
        if daily_cfg.get("enabled", True):
            dlm_schedules.append({
                "Name": "Daily-Physical-Calendar",
                "CreateRule": {
                    "Interval": 24,
                    "IntervalUnit": "HOURS",
                    "Times": [daily_cfg.get("time_utc", "01:00")]
                },
                "RetainRule": {
                    "Count": daily_cfg.get("retention_count", 7)
                },
                "CopyTags": True,
                "TagsToAdd": [
                    {"Key": "ScheduleTier", "Value": "Daily"},
                    {"Key": "ManagedBy", "Value": "AWS-DLM-Lifecycle-Calendar"}
                ]
            })

        # 2. Weekly Schedule (custom schedule)
        if weekly_cfg.get("enabled", True):
            dlm_schedules.append({
                "Name": "Weekly-Physical-Calendar",
                "CreateRule": {
                    "CronExpression": f"cron(0 2 ? * SUN *)"  # Weekly on Sunday
                },
                "RetainRule": {
                    "Count": weekly_cfg.get("retention_count", 4)
                },
                "CopyTags": True,
                "TagsToAdd": [
                    {"Key": "ScheduleTier", "Value": "Weekly"},
                    {"Key": "ManagedBy", "Value": "AWS-DLM-Lifecycle-Calendar"}
                ]
            })

        return {
            "Description": "Automated Physical Calendar Snapshot Lifecycle (AWS Learner Lab)",
            "ExecutionRoleArn": role_arn,
            "State": "ENABLED",
            "PolicyDetails": {
                "PolicyType": "EBS_SNAPSHOT_MANAGEMENT",
                "ResourceTypes": ["VOLUME"],
                "TargetTags": target_tags_list,
                "Schedules": dlm_schedules
            }
        }

    def deploy_dlm_policy(self) -> Dict[str, Any]:
        """Creates or updates the AWS DLM policy in AWS Learner Lab."""
        if self.aws.is_mock or not self.dlm:
            return {
                "status": "SIMULATED_SUCCESS",
                "policy_id": "policy-0mock123456789",
                "message": f"Simulated DLM policy deployment using {self.aws.get_lab_role_arn(self.lab_role_name)}.",
                "execution_role": self.aws.get_lab_role_arn(self.lab_role_name)
            }

        payload = self.build_dlm_policy_payload()
        try:
            response = self.dlm.create_lifecycle_policy(
                ExecutionRoleArn=payload["ExecutionRoleArn"],
                Description=payload["Description"],
                State=payload["State"],
                PolicyDetails=payload["PolicyDetails"]
            )
            return {
                "status": "DEPLOYED",
                "policy_id": response.get("PolicyId"),
                "message": "Successfully created DLM policy in AWS Learner Lab!",
                "execution_role": payload["ExecutionRoleArn"]
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "hint": "Check that your AWS credentials are valid and 'LabRole' exists."
            }

    def list_existing_policies(self) -> List[Dict[str, Any]]:
        """Lists active DLM policies in the AWS account."""
        if self.aws.is_mock or not self.dlm:
            return [
                {
                    "PolicyId": "policy-0mock123456789",
                    "Description": "Mock DLM Policy (AWS Learner Lab)",
                    "State": "ENABLED",
                    "PolicyType": "EBS_SNAPSHOT_MANAGEMENT"
                }
            ]
        try:
            res = self.dlm.get_lifecycle_policies()
            return res.get("Policies", [])
        except Exception:
            return []
