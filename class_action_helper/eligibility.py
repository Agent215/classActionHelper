from __future__ import annotations

from getpass import getpass
from typing import Any

from .models import append_history


def ask_eligibility_questions(settlement: dict[str, Any]) -> dict[str, str]:
    answers = dict(settlement.get("eligibility_answers") or {})
    questions = settlement.get("eligibility_questions") or []

    if not questions:
        print("No eligibility questions are configured for this settlement.")
        return answers

    for question in questions:
        question_id = question["id"]
        prompt = question["question"]
        question_type = question.get("type", "text")
        existing = answers.get(question_id)

        if question_type == "yes_no":
            answers[question_id] = _prompt_yes_no(prompt, existing)
        elif question_type == "secret_or_text":
            answers[question_id] = _prompt_secret_or_text(prompt, existing)
        else:
            answers[question_id] = _prompt_text(prompt, existing)

    return answers


def determine_status_from_answers(settlement: dict[str, Any]) -> str:
    answers = settlement.get("eligibility_answers") or {}
    questions = settlement.get("eligibility_questions") or []
    if not answers:
        return "needs_review"

    if settlement.get("requires_notice_id") and not _has_notice_id(answers):
        return "needs_notice_id"

    if settlement.get("requires_proof") and not _has_proof(answers):
        return "needs_proof"

    if settlement.get("requires_login") and not _is_yes(answers.get("login_completed")):
        return "needs_login"

    if _has_clear_disqualifying_no(questions, answers):
        return "not_eligible"

    if _all_configured_questions_answered(questions, answers):
        return "eligible"

    return "needs_review"


def apply_eligibility_answers(settlement: dict[str, Any], answers: dict[str, str]) -> str:
    settlement["eligibility_answers"] = answers
    status = determine_status_from_answers(settlement)
    old_status = settlement.get("status")
    settlement["status"] = status
    append_history(settlement, f"Eligibility answers saved; status {old_status} -> {status}.")
    return status


def _prompt_yes_no(prompt: str, existing: str | None) -> str:
    suffix = f" [{existing}]" if existing else " [yes/no]"
    while True:
        value = input(f"{prompt}{suffix}: ").strip().lower()
        if not value and existing:
            return str(existing)
        if value in {"y", "yes"}:
            return "yes"
        if value in {"n", "no"}:
            return "no"
        print("Please answer yes or no.")


def _prompt_secret_or_text(prompt: str, existing: str | None) -> str:
    suffix = " [saved; press Enter to keep]" if existing else ""
    value = getpass(f"{prompt}{suffix}: ").strip()
    if not value and existing:
        return str(existing)
    return value


def _prompt_text(prompt: str, existing: str | None) -> str:
    suffix = f" [{existing}]" if existing else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if not value and existing:
        return str(existing)
    return value


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
    if not proof_keys:
        return False
    return any(_is_yes(answers.get(key)) or bool(str(answers.get(key, "")).strip()) for key in proof_keys)


def _has_clear_disqualifying_no(questions: list[dict[str, Any]], answers: dict[str, Any]) -> bool:
    disqualifying_tokens = {
        "purchased",
        "purchase",
        "bought",
        "buy",
        "covered",
        "eligible",
        "qualify",
        "lived",
        "resided",
        "used",
        "owned",
    }
    non_disqualifying_ids = {"has_notice_id", "notice_id", "has_proof", "proof", "receipt"}
    for question in questions:
        question_id = str(question.get("id", ""))
        if question_id in non_disqualifying_ids:
            continue
        if question.get("type") != "yes_no":
            continue
        if str(answers.get(question_id, "")).strip().lower() != "no":
            continue
        text = f"{question_id} {question.get('question', '')}".lower()
        if any(token in text for token in disqualifying_tokens):
            return True
    return False


def _all_configured_questions_answered(questions: list[dict[str, Any]], answers: dict[str, Any]) -> bool:
    required_ids = [question.get("id") for question in questions if question.get("id")]
    return all(str(answers.get(question_id, "")).strip() for question_id in required_ids)
