from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from .models import normalize_settlement


ROOT = Path(__file__).resolve().parents[1]
SETTLEMENTS_PATH = ROOT / "settlements.yaml"
PROFILE_EXAMPLE_PATH = ROOT / "profile.local.example.json"
PROFILE_PATH = ROOT / "profile.local.json"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
ENV_PATH = ROOT / ".env"
SCREENSHOTS_DIR = ROOT / "screenshots"
CONFIRMATIONS_DIR = ROOT / "confirmations"
BROWSER_PROFILE_DIR = ROOT / "browser-profile"

ENV_PROFILE_MAP = {
    "first_name": "FIRST_NAME",
    "last_name": "LAST_NAME",
    "email": "EMAIL",
    "phone": "PHONE",
    "address1": "ADDRESS1",
    "address2": "ADDRESS2",
    "city": "CITY",
    "state": "STATE",
    "zip": "ZIP",
    "country": "COUNTRY",
    "payment_preference": "PAYMENT_PREFERENCE",
    "paypal_email": "PAYPAL_EMAIL",
    "venmo": "VENMO",
    "zelle_email_or_phone": "ZELLE_EMAIL_OR_PHONE",
}


def ensure_local_dirs() -> None:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    CONFIRMATIONS_DIR.mkdir(exist_ok=True)
    BROWSER_PROFILE_DIR.mkdir(exist_ok=True)


def load_settlements(path: Path = SETTLEMENTS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or []
    if isinstance(data, dict) and "settlements" in data:
        data = data["settlements"]
    if not isinstance(data, list):
        return data
    return [normalize_settlement(item or {}) for item in data]


def save_settlements(settlements: list[dict[str, Any]], path: Path = SETTLEMENTS_PATH) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(settlements, handle, sort_keys=False, allow_unicode=False)


def find_settlement(settlements: list[dict[str, Any]], settlement_id: str) -> dict[str, Any] | None:
    for settlement in settlements:
        if settlement.get("id") == settlement_id:
            return settlement
    return None


def init_profile() -> bool:
    if ENV_PATH.exists():
        return False
    shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)
    return True


def load_profile(path: Path = PROFILE_PATH) -> dict[str, Any]:
    if ENV_PATH.exists():
        return load_env_profile(ENV_PATH)
    if not path.exists():
        raise FileNotFoundError(".env does not exist. Run init-profile first.")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("profile.local.json must contain a JSON object.")
    return data


def load_env_profile(path: Path = ENV_PATH) -> dict[str, str]:
    values = _parse_env_file(path)
    profile: dict[str, str] = {}
    for field_name, env_name in ENV_PROFILE_MAP.items():
        profile[field_name] = values.get(env_name, values.get(f"PROFILE_{env_name}", ""))
    return profile


def save_env_profile(profile: dict[str, Any], path: Path = ENV_PATH) -> None:
    lines = [
        "# Private local profile for class-action-helper.",
        "# This file is ignored by git.",
    ]
    for field_name, env_name in ENV_PROFILE_MAP.items():
        value = str(profile.get(field_name, ""))
        lines.append(f"{env_name}={_quote_env_value(value)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            values[key] = value
    return values


def _quote_env_value(value: str) -> str:
    if not value:
        return ""
    if any(char.isspace() for char in value) or any(char in value for char in "'\"#="):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def export_csv(settlements: list[dict[str, Any]], path: Path) -> None:
    fields = [
        "id",
        "name",
        "status",
        "deadline",
        "requires_proof",
        "requires_notice_id",
        "confirmation_number",
        "official_url",
        "expected_benefit",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for settlement in settlements:
            writer.writerow({field: settlement.get(field, "") for field in fields})
