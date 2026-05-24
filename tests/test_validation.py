from __future__ import annotations

from datetime import date

from class_action_helper.eligibility import determine_status_from_answers
from class_action_helper.cli import _build_work_queue, build_parser
from class_action_helper.models import is_expired, validate_settlements
from class_action_helper.safety import SubmissionGuard


def settlement(**overrides):
    data = {
        "id": "sample",
        "name": "Sample",
        "official_url": "https://example.com/claim",
        "deadline": "2099-01-01",
        "eligibility_summary": "Example only.",
        "requires_notice_id": False,
        "requires_proof": False,
        "requires_login": False,
        "has_captcha_or_bot_check": False,
        "status": "todo",
        "eligibility_questions": [
            {
                "id": "purchased_product",
                "question": "Did you personally buy the covered product?",
                "type": "yes_no",
            }
        ],
        "eligibility_answers": {"purchased_product": "yes"},
    }
    data.update(overrides)
    return data


def test_validation_catches_duplicate_ids():
    report = validate_settlements([settlement(), settlement(name="Other")])
    assert any("duplicate settlement id" in error for error in report.errors)


def test_validation_catches_invalid_statuses():
    report = validate_settlements([settlement(status="made_up")])
    assert any("invalid status" in error for error in report.errors)


def test_validation_catches_invalid_dates():
    report = validate_settlements([settlement(deadline="01/01/2099")])
    assert any("deadline must use YYYY-MM-DD" in error for error in report.errors)


def test_expired_settlement_detection():
    assert is_expired(settlement(deadline="2020-01-01"), today=date(2021, 1, 1))
    assert not is_expired(settlement(deadline="2099-01-01"), today=date(2021, 1, 1))


def test_status_transitions_from_eligibility_answers():
    assert determine_status_from_answers(settlement()) == "eligible"
    assert determine_status_from_answers(settlement(eligibility_answers={"purchased_product": "no"})) == "not_eligible"
    assert (
        determine_status_from_answers(
            settlement(
                requires_notice_id=True,
                eligibility_answers={"purchased_product": "yes", "has_notice_id": "no"},
            )
        )
        == "needs_notice_id"
    )


def test_submission_guard_blocks_submitted_settlements(tmp_path):
    screenshot = tmp_path / "pre.png"
    screenshot.write_text("placeholder")
    guard = SubmissionGuard(settlement(status="submitted"))
    decision = guard.evaluate("SUBMIT sample", pre_submit_screenshot=screenshot)
    assert not decision.allowed
    assert any("already marked submitted" in reason for reason in decision.reasons)


def test_submission_guard_blocks_notice_id_required_but_missing(tmp_path):
    screenshot = tmp_path / "pre.png"
    screenshot.write_text("placeholder")
    guard = SubmissionGuard(settlement(requires_notice_id=True, eligibility_answers={"purchased_product": "yes"}))
    decision = guard.evaluate("SUBMIT sample", pre_submit_screenshot=screenshot)
    assert not decision.allowed
    assert any("Notice ID is required" in reason for reason in decision.reasons)


def test_submission_guard_requires_exact_submit_phrase(tmp_path):
    screenshot = tmp_path / "pre.png"
    screenshot.write_text("placeholder")
    guard = SubmissionGuard(settlement())
    decision = guard.evaluate("submit sample", pre_submit_screenshot=screenshot)
    assert not decision.allowed
    assert any("Typed approval must exactly match" in reason for reason in decision.reasons)


def test_work_queue_sorts_by_deadline_and_skips_blocked():
    settlements = [
        settlement(id="later", deadline="2099-02-01", status="todo"),
        settlement(id="blocked", deadline="2099-01-01", status="needs_notice_id"),
        settlement(id="earlier", deadline="2099-01-15", status="todo"),
    ]
    queue = _build_work_queue(
        settlements,
        settlement_id=None,
        limit=2,
        allow_expired=False,
        include_blocked=False,
    )
    assert [item["id"] for item in queue] == ["earlier", "later"]


def test_parser_includes_tui_command():
    args = build_parser().parse_args(["tui"])
    assert args.func.__name__ == "cmd_tui"
