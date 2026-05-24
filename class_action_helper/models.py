from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse


STATUSES = {
    "todo",
    "needs_review",
    "eligible",
    "not_eligible",
    "needs_notice_id",
    "needs_proof",
    "needs_login",
    "needs_manual_action",
    "started",
    "ready_for_review",
    "submitted",
    "skipped",
    "expired",
    "error",
}

REQUIRED_FIELDS = {
    "id",
    "name",
    "official_url",
    "deadline",
    "eligibility_summary",
    "requires_notice_id",
    "requires_proof",
    "requires_login",
    "has_captcha_or_bot_check",
    "status",
}

BOOLEAN_FIELDS = {
    "requires_notice_id",
    "requires_proof",
    "requires_login",
    "has_captcha_or_bot_check",
}

PROFILE_FIELDS = {
    "first_name",
    "last_name",
    "email",
    "phone",
    "address1",
    "address2",
    "city",
    "state",
    "zip",
    "country",
    "payment_preference",
    "paypal_email",
    "venmo",
    "zelle_email_or_phone",
}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: "ValidationReport") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "settlement"


def parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    return date.fromisoformat(value)


def is_expired(settlement: dict[str, Any], today: date | None = None) -> bool:
    today = today or date.today()
    return parse_date(settlement.get("deadline")) < today


def days_remaining(settlement: dict[str, Any], today: date | None = None) -> int:
    today = today or date.today()
    return (parse_date(settlement.get("deadline")) - today).days


def validate_url(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_placeholder_url(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    return urlparse(url).netloc.lower() in {"example.com", "www.example.com"}


def append_history(settlement: dict[str, Any], message: str) -> None:
    history = settlement.setdefault("history", [])
    history.append({"at": now_iso(), "message": message})
    settlement["updated_at"] = now_iso()


def new_settlement_id(name: str, existing_ids: set[str]) -> str:
    base = slugify(name)
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def normalize_settlement(settlement: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settlement)
    normalized.setdefault("class_period_start", "")
    normalized.setdefault("class_period_end", "")
    normalized.setdefault("expected_benefit", "")
    normalized.setdefault("confirmation_number", "")
    normalized.setdefault("confirmation_file", "")
    normalized.setdefault("notes", "")
    normalized.setdefault("eligibility_questions", [])
    normalized.setdefault("eligibility_answers", {})
    normalized.setdefault("form_strategy", {"fields": {}, "checkboxes": {}, "radios": {}})
    normalized.setdefault("created_at", now_iso())
    normalized.setdefault("updated_at", now_iso())
    normalized.setdefault("history", [])
    return normalized


def validate_settlements(settlements: list[dict[str, Any]]) -> ValidationReport:
    report = ValidationReport()
    seen_ids: set[str] = set()

    if not isinstance(settlements, list):
        report.errors.append("settlements.yaml must contain a YAML list of settlements.")
        return report

    for index, settlement in enumerate(settlements, start=1):
        label = settlement.get("id") or f"item #{index}"
        missing = sorted(field for field in REQUIRED_FIELDS if field not in settlement)
        for field_name in missing:
            report.errors.append(f"{label}: missing required field {field_name}.")

        settlement_id = settlement.get("id")
        if settlement_id in seen_ids:
            report.errors.append(f"{label}: duplicate settlement id.")
        elif settlement_id:
            seen_ids.add(settlement_id)

        status = settlement.get("status")
        if status and status not in STATUSES:
            report.errors.append(f"{label}: invalid status {status!r}.")

        if "deadline" in settlement:
            try:
                if is_expired(settlement):
                    report.warnings.append(f"{label}: deadline has passed.")
            except ValueError:
                report.errors.append(f"{label}: deadline must use YYYY-MM-DD format.")

        for field_name in ("class_period_start", "class_period_end"):
            value = settlement.get(field_name)
            if value:
                try:
                    parse_date(value)
                except ValueError:
                    report.errors.append(f"{label}: {field_name} must use YYYY-MM-DD format.")

        if "official_url" in settlement and not validate_url(settlement.get("official_url")):
            report.errors.append(f"{label}: official_url must be a valid http(s) URL.")

        for field_name in BOOLEAN_FIELDS:
            if field_name in settlement and not isinstance(settlement.get(field_name), bool):
                report.errors.append(f"{label}: {field_name} must be true or false.")

        questions = settlement.get("eligibility_questions", [])
        if questions and not isinstance(questions, list):
            report.errors.append(f"{label}: eligibility_questions must be a list.")
        for question in questions if isinstance(questions, list) else []:
            if not isinstance(question, dict) or not question.get("id") or not question.get("question"):
                report.errors.append(f"{label}: every eligibility question needs id and question.")

    return report


def validate_profile(profile: dict[str, Any]) -> ValidationReport:
    report = ValidationReport()
    if not isinstance(profile, dict):
        report.errors.append("profile.local.json must contain a JSON object.")
        return report

    unknown = sorted(set(profile) - PROFILE_FIELDS)
    for field_name in unknown:
        report.warnings.append(f"profile.local.json: unknown field {field_name}.")

    for field_name in sorted(PROFILE_FIELDS - set(profile)):
        report.warnings.append(f"profile.local.json: missing optional field {field_name}.")

    if profile.get("email") and "@" not in str(profile["email"]):
        report.errors.append("profile.local.json: email appears malformed.")

    return report
