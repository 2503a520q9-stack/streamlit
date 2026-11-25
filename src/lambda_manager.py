"""
AWS Lambda Manager:
Automates packaging, deployment, invocation, and EventBridge calendar scheduling
for the Snapshot Lifecycle Lambda function in AWS Learner Lab using 'LabRole'.
"""
import os
import io
import json
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional
from src.aws_client import AWSClientManager

FUNCTION_NAME = "SnapshotLifecyclePhysicalCalendar"
RULE_NAME = "SnapshotLifecycleCalendarCron"

class LambdaManager:
    def __init__(self, aws_client: AWSClientManager, role_name: str = "LabRole"):
        self.aws = aws_client
        self.role_name = role_name
        self.function_name = FUNCTION_NAME
        self.lambda_client = None if self.aws.is_mock else self.aws._session.client("lambda")
        self.events_client = None if self.aws.is_mock else self.aws._session.client("events")

    def build_deployment_package(self) -> bytes:
        """Packages lambda_function.py into an in-memory zip archive."""
        base_dir = Path(__file__).resolve().parent.parent
        lambda_file = base_dir / "src" / "lambda_function.py"

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            if lambda_file.exists():
                z.write(lambda_file, "lambda_function.py")
            else:
                raise FileNotFoundError(f"Lambda source file not found at {lambda_file}")

        zip_buffer.seek(0)
        return zip_buffer.read()

    def get_function_status(self) -> Dict[str, Any]:
        """Checks if the Lambda function is deployed and active."""
        if self.aws.is_mock or not self.lambda_client:
            return {
                "deployed": True,
                "function_name": self.function_name,
                "runtime": "python3.11",
                "role": self.aws.get_lab_role_arn(self.role_name),
                "state": "Active (Simulated)",
                "last_modified": "2026-11-22T12:00:00.000+0000"
            }

        try:
            res = self.lambda_client.get_function(FunctionName=self.function_name)
            cfg = res.get("Configuration", {})
            return {
                "deployed": True,
                "function_name": cfg.get("FunctionName"),
                "function_arn": cfg.get("FunctionArn"),
                "runtime": cfg.get("Runtime"),
                "role": cfg.get("Role"),
                "state": cfg.get("State", "Active"),
                "last_modified": cfg.get("LastModified"),
                "timeout": cfg.get("Timeout"),
                "memory_size": cfg.get("MemorySize")
            }
        except self.lambda_client.exceptions.ResourceNotFoundException:
            return {"deployed": False, "function_name": self.function_name}
        except Exception as e:
            return {"deployed": False, "error": str(e)}

    def deploy_function(self) -> Dict[str, Any]:
        """Deploys or updates the AWS Lambda function using LabRole."""
        role_arn = self.aws.get_lab_role_arn(self.role_name)
        zip_bytes = self.build_deployment_package()

        if self.aws.is_mock or not self.lambda_client:
            return {
                "status": "SIMULATED_DEPLOY",
                "function_name": self.function_name,
                "role_arn": role_arn,
                "message": f"Successfully simulated Lambda deployment using {role_arn}."
            }

        try:
            # Check if function already exists
            try:
                self.lambda_client.get_function(FunctionName=self.function_name)
                # Update existing function code
                res = self.lambda_client.update_function_code(
                    FunctionName=self.function_name,
                    ZipFile=zip_bytes
                )
                return {
                    "status": "UPDATED",
                    "function_name": self.function_name,
                    "function_arn": res.get("FunctionArn"),
                    "role_arn": role_arn,
                    "message": "Lambda function code updated successfully!"
                }
            except self.lambda_client.exceptions.ResourceNotFoundException:
                # Create new function
                res = self.lambda_client.create_function(
                    FunctionName=self.function_name,
                    Runtime="python3.11",
                    Role=role_arn,
                    Handler="lambda_function.lambda_handler",
                    Code={"ZipFile": zip_bytes},
                    Description="AWS Snapshot Lifecycle Physical Calendar Engine (Learner Lab)",
                    Timeout=120,
                    MemorySize=128
                )
                return {
                    "status": "CREATED",
                    "function_name": self.function_name,
                    "function_arn": res.get("FunctionArn"),
                    "role_arn": role_arn,
                    "message": "Lambda function created successfully!"
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "hint": "Ensure your AWS Learner Lab session is active and LabRole is authorized."
            }

    def setup_eventbridge_calendar_schedule(self, cron_expression: str = "cron(0 1 * * ? *)") -> Dict[str, Any]:
        """Configures Amazon EventBridge (CloudWatch Events) Rule to trigger Lambda on a physical calendar cron."""
        if self.aws.is_mock or not self.events_client:
            return {
                "status": "SIMULATED_SCHEDULE",
                "rule_name": RULE_NAME,
                "cron": cron_expression,
                "target": self.function_name,
                "message": f"Simulated EventBridge rule '{RULE_NAME}' mapped to cron '{cron_expression}'."
            }

        try:
            # 1. Put Rule
            rule_res = self.events_client.put_rule(
                Name=RULE_NAME,
                ScheduleExpression=cron_expression,
                State="ENABLED",
                Description="Triggers Snapshot Lifecycle Physical Calendar Lambda daily at 01:00 UTC"
            )
            rule_arn = rule_res.get("RuleArn")

            # 2. Get Lambda ARN
            fn_info = self.get_function_status()
            fn_arn = fn_info.get("function_arn")

            if fn_arn:
                # 3. Add target
                self.events_client.put_targets(
                    Rule=RULE_NAME,
                    Targets=[{"Id": "SnapshotLifecycleLambdaTarget", "Arn": fn_arn}]
                )

                # 4. Add permission for EventBridge to invoke Lambda
                try:
                    self.lambda_client.add_permission(
                        FunctionName=self.function_name,
                        StatementId="EventBridgeCalendarTrigger",
                        Action="lambda:InvokeFunction",
                        Principal="events.amazonaws.com",
                        SourceArn=rule_arn
                    )
                except Exception:
                    pass  # Permission may already exist

            return {
                "status": "CONFIGURED",
                "rule_name": RULE_NAME,
                "rule_arn": rule_arn,
                "cron": cron_expression,
                "message": "EventBridge physical calendar rule configured successfully!"
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def invoke_function(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invokes the AWS Lambda function and returns the execution response."""
        payload_dict = payload or {"mode": "ALL", "dry_run": False}

        if self.aws.is_mock or not self.lambda_client:
            from src.lambda_function import lambda_handler
            # Local simulated execution
            return {
                "status": "SIMULATED_EXECUTION",
                "response": lambda_handler(payload_dict, None)
            }

        try:
            res = self.lambda_client.invoke(
                FunctionName=self.function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload_dict)
            )
            raw_response = res["Payload"].read().decode("utf-8")
            parsed = json.loads(raw_response)
            return {
                "status": "SUCCESS",
                "status_code": res.get("StatusCode"),
                "response": parsed
            }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}
