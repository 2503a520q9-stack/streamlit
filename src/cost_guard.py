"""
Learner Lab Budget & Cost Guard:
Monitors EBS snapshot volume, calculates billing impact,
and ensures lab quotas are respected.
"""
from typing import List, Dict, Any

class CostGuard:
    def __init__(self,
                 total_budget_usd: float = 100.0,
                 ebs_cost_per_gb_month: float = 0.05,
                 alert_threshold_usd: float = 5.0):
        self.total_budget = total_budget_usd
        self.ebs_cost_per_gb_month = ebs_cost_per_gb_month
        self.alert_threshold_usd = alert_threshold_usd

    def calculate_snapshot_costs(self, snapshots: List[Dict[str, Any]], expired_count: int = 0, expired_gb: float = 0.0) -> Dict[str, Any]:
        """
        Calculates snapshot storage usage, estimated monthly costs,
        and potential savings from purging expired snapshots.
        """
        total_snaps = len(snapshots)
        total_gb = sum(s.get("VolumeSize", 0) for s in snapshots)

        monthly_cost = total_gb * self.ebs_cost_per_gb_month
        pct_of_budget = (monthly_cost / self.total_budget) * 100 if self.total_budget > 0 else 0

        potential_savings = expired_gb * self.ebs_cost_per_gb_month

        status = "HEALTHY"
        warning = None
        if monthly_cost >= self.alert_threshold_usd:
            status = "WARNING"
            warning = f"Estimated monthly snapshot cost (${monthly_cost:.2f}) exceeds alert threshold (${self.alert_threshold_usd:.2f})!"
        if pct_of_budget >= 15.0:
            status = "DANGER"
            warning = f"High snapshot storage! Consuming {pct_of_budget:.1f}% of your $100 Learner Lab credit."

        return {
            "total_snapshots": total_snaps,
            "total_gb": total_gb,
            "monthly_cost_usd": round(monthly_cost, 2),
            "learner_lab_budget_usd": self.total_budget,
            "budget_used_percentage": round(pct_of_budget, 1),
            "status": status,
            "warning": warning,
            "expired_snapshots": expired_count,
            "expired_gb": expired_gb,
            "reclaimable_savings_usd": round(potential_savings, 2)
        }
