"""
Physical Calendar Engine: handles calendar math, GFS schedules,
blackout/freeze dates, retention expiration calculations, and monthly calendar matrices.
"""
import calendar as py_cal
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

class CalendarEngine:
    def __init__(self, policy_config: Dict[str, Any]):
        self.policy = policy_config
        self.schedules = policy_config.get("schedules", {})
        self.blackouts = {b["date"]: b["reason"] for b in policy_config.get("blackout_calendar", [])}

    def is_blackout(self, check_date: date) -> Optional[str]:
        """Returns blackout reason if check_date is a freeze date, otherwise None."""
        date_str = check_date.strftime("%Y-%m-%d")
        return self.blackouts.get(date_str)

    def get_applicable_tiers_for_date(self, check_date: date) -> List[Dict[str, Any]]:
        """
        Determines which backup tiers (Daily, Weekly, Monthly, Yearly)
        are scheduled to run on the given physical calendar date.
        """
        applicable = []
        date_str = check_date.strftime("%Y-%m-%d")

        # Check if today is a freeze/blackout window
        if date_str in self.blackouts:
            return []

        # 1. Daily Schedule
        daily = self.schedules.get("daily", {})
        if daily.get("enabled", True):
            applicable.append({
                "tier": "Daily",
                "time_utc": daily.get("time_utc", "01:00"),
                "retention_days": daily.get("retention_days", 7),
                "retention_count": daily.get("retention_count", 7),
                "description": daily.get("description", "Daily snapshot")
            })

        # 2. Weekly Schedule (e.g. Sunday)
        weekly = self.schedules.get("weekly", {})
        if weekly.get("enabled", True):
            target_day = weekly.get("day_of_week", "Sunday").capitalize()
            current_day_name = check_date.strftime("%A")
            if current_day_name == target_day:
                applicable.append({
                    "tier": "Weekly",
                    "time_utc": weekly.get("time_utc", "02:00"),
                    "retention_days": weekly.get("retention_days", 28),
                    "retention_count": weekly.get("retention_count", 4),
                    "description": weekly.get("description", "Weekly snapshot")
                })

        # 3. Monthly Schedule (e.g. 1st day of month)
        monthly = self.schedules.get("monthly", {})
        if monthly.get("enabled", True):
            target_day_of_month = monthly.get("day_of_month", 1)
            if check_date.day == target_day_of_month:
                applicable.append({
                    "tier": "Monthly",
                    "time_utc": monthly.get("time_utc", "03:00"),
                    "retention_days": monthly.get("retention_days", 365),
                    "retention_count": monthly.get("retention_count", 12),
                    "description": monthly.get("description", "Monthly snapshot")
                })

        # 4. Yearly Schedule (e.g. Jan 1st)
        yearly = self.schedules.get("yearly", {})
        if yearly.get("enabled", True):
            target_month = yearly.get("month", 1)
            target_dom = yearly.get("day_of_month", 1)
            if check_date.month == target_month and check_date.day == target_dom:
                applicable.append({
                    "tier": "Yearly",
                    "time_utc": yearly.get("time_utc", "04:00"),
                    "retention_days": yearly.get("retention_days", 1095),
                    "retention_count": yearly.get("retention_count", 3),
                    "description": yearly.get("description", "Yearly snapshot")
                })

        return applicable

    def calculate_expiration_date(self, create_date: date, retention_days: int) -> date:
        """Calculates exact physical calendar date when snapshot should be purged."""
        return create_date + timedelta(days=retention_days)

    def generate_projection(self, start_date: date, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Generates upcoming calendar event forecast for the next N days."""
        projection = []
        for i in range(days_ahead):
            curr_date = start_date + timedelta(days=i)
            blackout_reason = self.is_blackout(curr_date)
            tiers = self.get_applicable_tiers_for_date(curr_date)

            projection.append({
                "date": curr_date.strftime("%Y-%m-%d"),
                "day_name": curr_date.strftime("%A"),
                "is_blackout": blackout_reason is not None,
                "blackout_reason": blackout_reason,
                "scheduled_tiers": [t["tier"] for t in tiers],
                "tier_details": tiers
            })
        return projection

    def get_month_calendar_matrix(self, year: int, month: int) -> List[List[Dict[str, Any]]]:
        """
        Builds a full 2D calendar grid (weeks x 7 days) annotated with:
        - Day number
        - Is today
        - Is blackout
        - Scheduled tiers
        """
        today = date.today()
        cal = py_cal.Calendar(firstweekday=0)  # Starts Monday
        weeks = cal.monthdayscalendar(year, month)

        grid = []
        for week in weeks:
            week_days = []
            for day_num in week:
                if day_num == 0:
                    week_days.append({"day": None, "date_str": None, "tiers": [], "is_blackout": False, "is_today": False})
                else:
                    d = date(year, month, day_num)
                    tiers = self.get_applicable_tiers_for_date(d)
                    blackout = self.is_blackout(d)
                    week_days.append({
                        "day": day_num,
                        "date_str": d.strftime("%Y-%m-%d"),
                        "tiers": [t["tier"] for t in tiers],
                        "is_blackout": blackout is not None,
                        "blackout_reason": blackout,
                        "is_today": (d == today)
                    })
            grid.append(week_days)
        return grid

    def is_snapshot_expired(self, snapshot: Dict[str, Any], current_date: date) -> Dict[str, Any]:
        """Determines if a given snapshot is expired."""
        tags = {t.get("Key", ""): t.get("Value", "") for t in snapshot.get("Tags", [])}
        tier = tags.get("ScheduleTier", "Daily")
        cal_date_str = tags.get("CalendarDate")
        expire_on_str = tags.get("ExpireOn")

        if cal_date_str:
            try:
                snap_date = datetime.strptime(cal_date_str, "%Y-%m-%d").date()
            except ValueError:
                snap_date = snapshot["StartTime"].date()
        else:
            snap_date = snapshot["StartTime"].date()

        if expire_on_str:
            try:
                expire_date = datetime.strptime(expire_on_str, "%Y-%m-%d").date()
            except ValueError:
                expire_date = None
        else:
            expire_date = None

        if not expire_date:
            tier_info = self.schedules.get(tier.lower(), {})
            retention_days = tier_info.get("retention_days", 7)
            expire_date = self.calculate_expiration_date(snap_date, retention_days)

        is_expired = current_date > expire_date
        days_remaining = (expire_date - current_date).days

        return {
            "snapshot_id": snapshot.get("SnapshotId"),
            "volume_id": snapshot.get("VolumeId"),
            "tier": tier,
            "created_date": snap_date.strftime("%Y-%m-%d"),
            "expire_date": expire_date.strftime("%Y-%m-%d"),
            "is_expired": is_expired,
            "days_remaining": days_remaining,
            "status": "EXPIRED" if is_expired else ("EXPIRING_SOON" if days_remaining <= 1 else "ACTIVE")
        }
