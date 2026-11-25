"""
AWS Client Manager: Provides boto3 EC2/DLM clients configured for AWS Learner Lab.
Supports session tokens, LabRole resolution, and mock fallback.
"""
import os
import boto3
from typing import Optional, Tuple, Dict, Any
from src.mock_provider import MockAWSProvider

class AWSClientManager:
    def __init__(self,
                 access_key: Optional[str] = None,
                 secret_key: Optional[str] = None,
                 session_token: Optional[str] = None,
                 region: str = "us-east-1",
                 force_mock: bool = False):
        self.access_key = access_key or os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("aws_access_key_id")
        self.secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("aws_secret_access_key")
        self.session_token = session_token or os.getenv("AWS_SESSION_TOKEN") or os.getenv("aws_session_token")
        self.region = region or os.getenv("AWS_DEFAULT_REGION") or os.getenv("aws_default_region") or "us-east-1"
        self.force_mock = force_mock

        self.is_mock = False
        self.account_id = "123456789012"
        self.user_arn = "arn:aws:sts::123456789012:assumed-role/LabRole/LearnerUser"
        self.mock_provider = None
        self._session = None
        self._ec2_client = None

        self._initialize()

    def _initialize(self):
        if self.force_mock or not (self.access_key and self.secret_key):
            self._use_mock("No AWS credentials provided or mock mode forced.")
            return

        try:
            self._session = boto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                aws_session_token=self.session_token,
                region_name=self.region
            )
            # Verify credentials with STS
            sts = self._session.client("sts")
            identity = sts.get_caller_identity()
            self.account_id = identity.get("Account", "unknown")
            self.user_arn = identity.get("Arn", "unknown")
            self._ec2_client = self._session.client("ec2")
            self.is_mock = False
        except Exception as e:
            self._use_mock(f"AWS connection failed ({str(e)}). Falling back to Mock Simulator.")

    def _use_mock(self, reason: str):
        self.is_mock = True
        self.mock_reason = reason
        self.mock_provider = MockAWSProvider()

    def get_ec2_client(self):
        if self.is_mock:
            return self.mock_provider
        return self._ec2_client

    def get_dlm_client(self):
        if self.is_mock:
            return None
        return self._session.client("dlm")

    def get_lab_role_arn(self, role_name: str = "LabRole") -> str:
        """Constructs or retrieves the Learner Lab IAM role ARN."""
        return f"arn:aws:iam::{self.account_id}:role/{role_name}"

    def get_connection_info(self) -> Dict[str, Any]:
        return {
            "is_mock": self.is_mock,
            "region": self.region,
            "account_id": self.account_id,
            "user_arn": self.user_arn,
            "lab_role_arn": self.get_lab_role_arn(),
            "reason": getattr(self, "mock_reason", "Connected to Live AWS Learner Lab")
        }
