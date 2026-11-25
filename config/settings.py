"""
Settings loader for AWS Snapshot Lifecycle Physical Calendar.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "calendar_policy.json"

def load_policy_config() -> dict:
    """Loads calendar policy configuration from JSON file."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_policy_config(config: dict) -> None:
    """Saves updated policy configuration back to JSON."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# AWS Settings
DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")

# Learner Lab Settings
LAB_ROLE_NAME = os.getenv("AWS_LAB_ROLE_NAME", "LabRole")
IS_MOCK_MODE = os.getenv("MOCK_AWS", "false").lower() in ("true", "1", "yes")
