from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GuardDecision:
    allowed: bool
    result: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class SubmitResult:
    result: str
    message: str
    confirmation_number: str = ""
    screenshot_path: str = ""


class SubmissionGuard:
    def __init__(self, settlement: dict[str, Any]) -> None:
        self.settlement = settlement

    def evaluate(
        self,
        typed_submit: str,
        *,
        pre_submit_screenshot: str | Path | None,
        captcha_detected: bool = False,
        certification_text: str = "",
        typed_certification: str = "",
        allow_missing_eligibility: bool = False,
        allow_unresolved_requirements: bool = False,
    ) -> GuardDecision:
        reasons: list[str] = []
        settlement_id = str(self.settlement.get("id", ""))

        if self.settlement.get("status") == "submitted":
            reasons.append("Settlement is already marked submitted.")

        if not allow_missing_eligibility and not self.settlement.get("eligibility_answers"):
            reasons.append("Eligibility answers have not been saved.")

        expected_submit = f"SUBMIT {settlement_id}"
        if typed_submit != expected_submit:
            reasons.append(f"Typed approval must exactly match {expected_submit!r}.")

        if captcha_detected or self.settlement.get("has_captcha_or_bot_check"):
            reasons.append("Visible or configured CAPTCHA/bot check requires manual action.")

        if not pre_submit_screenshot or not Path(pre_submit_screenshot).exists():
            reasons.append("A visible pre-submit review screenshot must be saved before submission.")

        if certification_text:
            expected_certify = f"CERTIFY {settlement_id}"
            if typed_certification != expected_certify:
                reasons.append(f"Certification approval must exactly match {expected_certify!r}.")

        if not allow_unresolved_requirements:
            reasons.extend(self._unresolved_requirement_reasons())

        if reasons:
            return GuardDecision(False, "blocked", reasons)
        return GuardDecision(True, "allowed", [])

    def _unresolved_requirement_reasons(self) -> list[str]:
        answers = self.settlement.get("eligibility_answers") or {}
        reasons: list[str] = []

        if self.settlement.get("requires_notice_id") and not _has_notice_id(answers):
            reasons.append("Notice ID is required but no notice ID answer is saved.")

        if self.settlement.get("requires_proof") and not _has_proof(answers):
            reasons.append("Proof is required but no proof answer is saved.")

        if self.settlement.get("requires_login") and not _is_yes(answers.get("login_completed")):
            reasons.append("Login is required and has not been marked completed.")

        return reasons


def _is_yes(value: Any) -> bool:
    return str(value).strip().lower() in {"yes", "y", "true", "1"}


def _has_notice_id(answers: dict[str, Any]) -> bool:
    if _is_yes(answers.get("has_notice_id")) and str(answers.get("notice_id", "")).strip():
        return True
    for key, value in answers.items():
        if key == "has_notice_id":
            continue
        normalized_value = str(value).strip().lower()
        if "notice" in key and "id" in key and normalized_value and normalized_value not in {"no", "n", "false", "0"}:
            return True
    return False


def _has_proof(answers: dict[str, Any]) -> bool:
    proof_keys = [key for key in answers if "proof" in key or "receipt" in key or "document" in key]
    return bool(proof_keys) and any(_is_yes(answers.get(key)) or str(answers.get(key, "")).strip() for key in proof_keys)
