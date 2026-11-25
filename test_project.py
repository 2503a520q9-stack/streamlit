"""
Automated Test Suite for AWS Snapshot Lifecycle Physical Calendar.
Runs all component unit tests in local mock mode without needing live AWS credentials.
"""
import unittest
from datetime import date, timedelta
from config.settings import load_policy_config
from src.aws_client import AWSClientManager
from src.calendar_engine import CalendarEngine
from src.snapshot_manager import SnapshotManager
from src.cost_guard import CostGuard
from src.dlm_manager import DLMManager
from src.iam_manager import IAMManager
from src.ec2_manager import EC2Manager
from src.lambda_manager import LambdaManager
from src.lambda_function import lambda_handler

class TestSnapshotLifecycleCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy_config()
        cls.aws = AWSClientManager(force_mock=True)
        cls.cal = CalendarEngine(cls.policy)
        cls.sm = SnapshotManager(cls.aws, cls.cal, cls.policy)
        cls.guard = CostGuard()
        cls.dlm = DLMManager(cls.aws, cls.policy)
        cls.iam = IAMManager(cls.aws)
        cls.ec2_mgr = EC2Manager(cls.aws)
        cls.lambda_mgr = LambdaManager(cls.aws)

    def test_01_calendar_engine_daily_schedule(self):
        """Verify daily schedule triggers on normal days."""
        test_day = date(2026, 6, 10)
        tiers = self.cal.get_applicable_tiers_for_date(test_day)
        tier_names = [t["tier"] for t in tiers]
        self.assertIn("Daily", tier_names)

    def test_02_calendar_engine_weekly_schedule(self):
        """Verify weekly schedule triggers on Sunday."""
        test_sunday = date(2026, 6, 14)
        tiers = self.cal.get_applicable_tiers_for_date(test_sunday)
        tier_names = [t["tier"] for t in tiers]
        self.assertIn("Daily", tier_names)
        self.assertIn("Weekly", tier_names)

    def test_03_calendar_engine_monthly_schedule(self):
        """Verify monthly schedule triggers on the 1st of the month."""
        test_first = date(2026, 7, 1)
        tiers = self.cal.get_applicable_tiers_for_date(test_first)
        tier_names = [t["tier"] for t in tiers]
        self.assertIn("Monthly", tier_names)

    def test_04_calendar_engine_blackout(self):
        """Verify blackout dates suppress snapshot scheduling."""
        blackout_day = date(2026, 12, 25)
        reason = self.cal.is_blackout(blackout_day)
        self.assertIsNotNone(reason)
        tiers = self.cal.get_applicable_tiers_for_date(blackout_day)
        self.assertEqual(len(tiers), 0)

    def test_05_expiration_calculation(self):
        """Verify retention days calculate correct expiration date."""
        create_d = date(2026, 1, 1)
        expire_d = self.cal.calculate_expiration_date(create_d, 7)
        self.assertEqual(expire_d, date(2026, 1, 8))

    def test_06_snapshot_manager_volume_listing(self):
        """Verify volume listing and target tag recognition."""
        volumes = self.sm.list_volumes()
        self.assertGreater(len(volumes), 0)
        target_vols = [v for v in volumes if v["IsBackupTarget"]]
        self.assertGreater(len(target_vols), 0)

    def test_07_retention_audit_and_purge_dry_run(self):
        """Verify retention auditor flags expired snapshots and dry-run purge."""
        audit = self.sm.audit_retention()
        self.assertIn("expired_count", audit)
        self.assertGreaterEqual(audit["expired_count"], 1)

        purge_res = self.sm.purge_expired_snapshots(dry_run=True)
        self.assertTrue(purge_res["dry_run"])
        self.assertEqual(purge_res["purged_count"], audit["expired_count"])

    def test_08_budget_guard_calculation(self):
        """Verify cost calculation against Learner Lab $100 budget."""
        mock_snaps = [{"VolumeSize": 20}, {"VolumeSize": 50}]
        cost = self.guard.calculate_snapshot_costs(mock_snaps)
        self.assertEqual(cost["total_gb"], 70)
        self.assertEqual(cost["monthly_cost_usd"], 3.50)
        self.assertEqual(cost["status"], "HEALTHY")

    def test_09_dlm_payload_lab_role(self):
        """Verify DLM policy payload correctly uses LabRole for Learner Lab."""
        payload = self.dlm.build_dlm_policy_payload()
        self.assertIn("ExecutionRoleArn", payload)
        self.assertTrue(payload["ExecutionRoleArn"].endswith(":role/LabRole"))
        self.assertEqual(payload["PolicyDetails"]["PolicyType"], "EBS_SNAPSHOT_MANAGEMENT")

    def test_10_iam_lab_role_inspection(self):
        """Verify IAM manager properly resolves LabRole for Learner Lab."""
        role_info = self.iam.inspect_lab_role()
        self.assertTrue(role_info["is_learner_lab_compliant"])
        self.assertTrue(role_info["role_arn"].endswith(":role/LabRole"))

    def test_11_ec2_instances_listing(self):
        """Verify EC2 manager identifies instances and block devices."""
        instances = self.ec2_mgr.list_instances()
        self.assertGreater(len(instances), 0)
        inst = instances[0]
        self.assertIn("BlockDevices", inst)
        self.assertGreater(len(inst["BlockDevices"]), 0)

    def test_12_lambda_deployment_packaging(self):
        """Verify Lambda manager builds valid zip deployment package."""
        zip_bytes = self.lambda_mgr.build_deployment_package()
        self.assertGreater(len(zip_bytes), 0)

    def test_13_lambda_handler_execution(self):
        """Verify Lambda function executes and returns HTTP 200 with calendar results."""
        event = {"mode": "SNAPSHOT", "custom_date": "2026-06-10"}
        response = lambda_handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("body", response)
        self.assertEqual(response["body"]["mode"], "SNAPSHOT")

    def test_14_volume_restoration_from_snapshot(self):
        """Verify disaster recovery volume restoration from snapshot."""
        snaps = self.sm.list_managed_snapshots()
        self.assertGreater(len(snaps), 0)
        target_snap = snaps[0]["SnapshotId"]
        restore_res = self.sm.restore_volume_from_snapshot(target_snap)
        self.assertEqual(restore_res["status"], "SUCCESS")
        self.assertIn("vol-", restore_res["volume_id"])

    def test_15_month_calendar_matrix_generation(self):
        """Verify monthly calendar matrix generates 7-column grid with annotated days."""
        matrix = self.cal.get_month_calendar_matrix(2026, 11)
        self.assertGreaterEqual(len(matrix), 4)
        for week in matrix:
            self.assertEqual(len(week), 7)

    def test_16_dr_readiness_assessment(self):
        """Verify disaster recovery assessment calculates score and coverage."""
        dr = self.sm.run_dr_assessment()
        self.assertIn("dr_score", dr)
        self.assertIn("coverage_percentage", dr)
        self.assertGreaterEqual(dr["dr_score"], 0)

if __name__ == "__main__":
    unittest.main()
