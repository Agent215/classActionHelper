from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
import sys
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None
    Table = None

from .browser import run_assisted_application
from .eligibility import apply_eligibility_answers, ask_eligibility_questions
from .models import (
    STATUSES,
    append_history,
    days_remaining,
    is_expired,
    is_placeholder_url,
    new_settlement_id,
    now_iso,
    parse_date,
    validate_profile,
    validate_settlements,
    validate_url,
)
from .storage import (
    ENV_PATH,
    PROFILE_PATH,
    SETTLEMENTS_PATH,
    ensure_local_dirs,
    export_csv,
    find_settlement,
    init_profile,
    load_env_profile,
    load_profile,
    load_settlements,
    save_env_profile,
    save_settlements,
)


console = Console() if Console else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claimBot")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("init-profile").set_defaults(func=cmd_init_profile)
    subcommands.add_parser("setup").set_defaults(func=cmd_setup)
    subcommands.add_parser("list").set_defaults(func=cmd_list)
    subcommands.add_parser("add").set_defaults(func=cmd_add)

    import_csv = subcommands.add_parser("import-csv")
    import_csv.add_argument("path")
    import_csv.set_defaults(func=cmd_import_csv)

    edit = subcommands.add_parser("edit")
    edit.add_argument("--id", required=True)
    edit.set_defaults(func=cmd_edit)

    subcommands.add_parser("validate").set_defaults(func=cmd_validate)

    eligibility = subcommands.add_parser("eligibility")
    eligibility.add_argument("--id", required=True)
    eligibility.set_defaults(func=cmd_eligibility)

    apply = subcommands.add_parser("apply")
    add_browser_args(apply)
    apply.add_argument("--id", required=True)
    apply.add_argument("--allow-expired", action="store_true")
    apply.set_defaults(func=cmd_apply)

    manual = subcommands.add_parser("manual-submit")
    add_browser_args(manual)
    manual.add_argument("--id", required=True)
    manual.add_argument("--allow-expired", action="store_true")
    manual.set_defaults(func=cmd_manual_submit)

    mark = subcommands.add_parser("mark")
    mark.add_argument("--id", required=True)
    mark.add_argument("--status", required=True, choices=sorted(STATUSES))
    mark.add_argument("--note", default="")
    mark.set_defaults(func=cmd_mark)

    export = subcommands.add_parser("export")
    export.add_argument("--output", default="settlements-export.csv")
    export.set_defaults(func=cmd_export)

    return parser


def add_browser_args(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headed", action="store_true", help="Run browser headed. This is the default.")
    mode.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument("--slow-mo", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-submit", action="store_true")
    parser.add_argument("--overwrite", action="store_true")


def cmd_init_profile(_: argparse.Namespace) -> int:
    created = init_profile()
    if created:
        _print(f"Created {ENV_PATH.name}. This file is private and gitignored.")
    else:
        _print(f"{ENV_PATH.name} already exists; leaving it unchanged.")
    return 0


def cmd_setup(_: argparse.Namespace) -> int:
    ensure_local_dirs()
    _print("First-run setup. Values are stored only in .env, which is ignored by git.")

    existing = load_env_profile() if ENV_PATH.exists() else {}
    defaults = {
        "city": existing.get("city") or "Philadelphia",
        "state": existing.get("state") or "PA",
        "country": existing.get("country") or "United States",
    }
    profile = dict(existing)

    required_fields = [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("address1", "Address line 1"),
        ("city", "City"),
        ("state", "State"),
        ("zip", "ZIP/postal code"),
        ("country", "Country"),
    ]
    optional_fields = [
        ("address2", "Address line 2"),
        ("payment_preference", "Payment preference"),
        ("paypal_email", "PayPal email"),
        ("venmo", "Venmo"),
        ("zelle_email_or_phone", "Zelle email or phone"),
    ]

    for field_name, label in required_fields:
        profile[field_name] = _prompt_setup_value(label, profile.get(field_name) or defaults.get(field_name, ""), required=True)
    for field_name, label in optional_fields:
        profile[field_name] = _prompt_setup_value(label, profile.get(field_name, ""), required=False)

    save_env_profile(profile)
    _print(f"Saved private profile to {ENV_PATH.name}.")

    csv_path = input("Optional tracker CSV to import now (press Enter to skip): ").strip()
    if csv_path:
        imported, updated = import_csv_file(Path(csv_path).expanduser())
        _print(f"Imported {imported} new settlements and updated {updated} existing settlements.")

    return cmd_validate(argparse.Namespace())


def cmd_list(_: argparse.Namespace) -> int:
    settlements = sorted(load_settlements(), key=lambda item: str(item.get("deadline", "")))
    if Table and console:
        table = Table(title="Settlements")
        for column in ("ID", "Name", "Status", "Deadline", "Days", "Proof", "Notice ID"):
            table.add_column(column)
        for settlement in settlements:
            days = _safe_days_remaining(settlement)
            style = "red" if days is not None and days < 0 else "yellow" if days is not None and days <= 14 else ""
            table.add_row(
                str(settlement.get("id", "")),
                str(settlement.get("name", "")),
                str(settlement.get("status", "")),
                str(settlement.get("deadline", "")),
                "?" if days is None else str(days),
                _yes_no(settlement.get("requires_proof")),
                _yes_no(settlement.get("requires_notice_id")),
                style=style,
            )
        console.print(table)
    else:
        for settlement in settlements:
            days = _safe_days_remaining(settlement)
            print(
                f"{settlement.get('id')} | {settlement.get('status')} | {settlement.get('deadline')} | "
                f"days={days} | proof={_yes_no(settlement.get('requires_proof'))} | "
                f"notice_id={_yes_no(settlement.get('requires_notice_id'))}"
            )
    return 0


def cmd_add(_: argparse.Namespace) -> int:
    settlements = load_settlements()
    existing_ids = {str(item.get("id")) for item in settlements}
    name = _required_prompt("Name")
    official_url = _prompt_valid_url("Official URL")
    deadline = _prompt_valid_date("Deadline (YYYY-MM-DD)")
    settlement = {
        "id": new_settlement_id(name, existing_ids),
        "name": name,
        "official_url": official_url,
        "deadline": deadline,
        "class_period_start": _prompt("Class period start (YYYY-MM-DD, optional)"),
        "class_period_end": _prompt("Class period end (YYYY-MM-DD, optional)"),
        "eligibility_summary": _required_prompt("Eligibility summary"),
        "requires_notice_id": _prompt_bool("Requires notice ID?"),
        "requires_proof": _prompt_bool("Requires proof?"),
        "requires_login": _prompt_bool("Requires login?"),
        "has_captcha_or_bot_check": _prompt_bool("Has CAPTCHA or bot check?"),
        "expected_benefit": _prompt("Expected benefit"),
        "status": "todo",
        "confirmation_number": "",
        "confirmation_file": "",
        "notes": _prompt("Notes"),
        "eligibility_questions": [],
        "eligibility_answers": {},
        "form_strategy": {"fields": {}, "checkboxes": {}, "radios": {}},
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "history": [{"at": now_iso(), "message": "Settlement added manually."}],
    }
    settlements.append(settlement)
    save_settlements(settlements)
    _print(f"Added settlement {settlement['id']}. Edit settlements.yaml to add eligibility questions or form strategy.")
    return 0


def cmd_import_csv(args: argparse.Namespace) -> int:
    source = Path(args.path).expanduser()
    try:
        imported, updated = import_csv_file(source)
    except FileNotFoundError:
        _print(f"CSV not found: {source}")
        return 1

    _print(f"Imported {imported} new settlements and updated {updated} existing settlements.")
    _print("Rows without URLs use https://example.com/claim and are blocked from apply until replaced.")
    return 0


def import_csv_file(source: Path) -> tuple[int, int]:
    if not source.exists():
        raise FileNotFoundError(source)

    settlements = load_settlements()
    by_id = {str(item.get("id")): item for item in settlements}
    imported = 0
    updated = 0

    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw_id = (row.get("id") or row.get("name") or "").strip()
            if not raw_id:
                continue
            settlement_id = raw_id
            official_url = (row.get("official_or_info_url") or "").strip() or "https://example.com/claim"
            status = _status_from_hint(row.get("status_hint", ""))
            imported_settlement = {
                "id": settlement_id,
                "name": (row.get("name") or settlement_id).strip(),
                "official_url": official_url,
                "deadline": (row.get("deadline") or "").strip(),
                "class_period_start": "",
                "class_period_end": "",
                "eligibility_summary": (row.get("eligibility_summary") or "").strip(),
                "requires_notice_id": _csv_truthy(row.get("requires_notice_id", "")),
                "requires_proof": _csv_truthy(row.get("requires_proof", "")),
                "requires_login": _csv_truthy(row.get("requires_login_or_validation", "")),
                "has_captcha_or_bot_check": False,
                "expected_benefit": (row.get("expected_benefit") or "").strip(),
                "status": status,
                "confirmation_number": "",
                "confirmation_file": "",
                "notes": _csv_notes(row),
                "eligibility_questions": _default_questions_for_row(row),
                "eligibility_answers": {},
                "form_strategy": {"fields": {}, "checkboxes": {}, "radios": {}},
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "history": [{"at": now_iso(), "message": f"Imported from {source.name}."}],
            }
            if settlement_id in by_id:
                existing = by_id[settlement_id]
                for field in (
                    "name",
                    "official_url",
                    "deadline",
                    "eligibility_summary",
                    "requires_notice_id",
                    "requires_proof",
                    "requires_login",
                    "expected_benefit",
                    "notes",
                    "eligibility_questions",
                ):
                    existing[field] = imported_settlement[field]
                existing["updated_at"] = now_iso()
                append_history(existing, f"Updated from {source.name}.")
                updated += 1
            else:
                settlements.append(imported_settlement)
                by_id[settlement_id] = imported_settlement
                imported += 1

    save_settlements(settlements)
    return imported, updated


def cmd_edit(args: argparse.Namespace) -> int:
    settlements = load_settlements()
    settlement = _require_settlement(settlements, args.id)
    editable = [
        "name",
        "official_url",
        "deadline",
        "class_period_start",
        "class_period_end",
        "eligibility_summary",
        "requires_notice_id",
        "requires_proof",
        "requires_login",
        "has_captcha_or_bot_check",
        "expected_benefit",
        "notes",
        "status",
    ]
    for field in editable:
        current = settlement.get(field, "")
        value = input(f"{field} [{current}]: ").strip()
        if not value:
            continue
        if field in {"requires_notice_id", "requires_proof", "requires_login", "has_captcha_or_bot_check"}:
            settlement[field] = value.lower() in {"y", "yes", "true", "1"}
        elif field == "deadline":
            parse_date(value)
            settlement[field] = value
        elif field == "official_url":
            if not validate_url(value):
                raise SystemExit("Invalid URL.")
            settlement[field] = value
        elif field == "status":
            if value not in STATUSES:
                raise SystemExit(f"Invalid status. Valid statuses: {', '.join(sorted(STATUSES))}")
            settlement[field] = value
        else:
            settlement[field] = value
    append_history(settlement, "Settlement edited interactively.")
    save_settlements(settlements)
    _print(f"Updated {args.id}.")
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    settlements = load_settlements()
    report = validate_settlements(settlements)
    if ENV_PATH.exists() or PROFILE_PATH.exists():
        try:
            report.extend(validate_profile(load_profile()))
        except Exception as exc:
            report.errors.append(str(exc))

    for warning in report.warnings:
        _print(f"Warning: {warning}")
    for error in report.errors:
        _print(f"Error: {error}")
    _print("Validation passed." if report.ok else "Validation failed.")
    return 0 if report.ok else 1


def cmd_eligibility(args: argparse.Namespace) -> int:
    settlements = load_settlements()
    settlement = _require_settlement(settlements, args.id)
    answers = ask_eligibility_questions(settlement)
    status = apply_eligibility_answers(settlement, answers)
    save_settlements(settlements)
    _print(f"Saved eligibility answers. New status: {status}.")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    return _run_browser_flow(args, manual_only=False)


def cmd_manual_submit(args: argparse.Namespace) -> int:
    return _run_browser_flow(args, manual_only=True)


def cmd_mark(args: argparse.Namespace) -> int:
    settlements = load_settlements()
    settlement = _require_settlement(settlements, args.id)
    old_status = settlement.get("status")
    settlement["status"] = args.status
    message = f"Manual status change {old_status} -> {args.status}."
    if args.note:
        message += f" Note: {args.note}"
        settlement["notes"] = f"{settlement.get('notes', '')}\n{args.note}".strip()
    append_history(settlement, message)
    save_settlements(settlements)
    _print(f"Marked {args.id} as {args.status}.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    output = Path(args.output)
    export_csv(load_settlements(), output)
    _print(f"Exported {output}.")
    return 0


def _run_browser_flow(args: argparse.Namespace, *, manual_only: bool) -> int:
    settlements = load_settlements()
    settlement = _require_settlement(settlements, args.id)

    if is_placeholder_url(settlement.get("official_url")):
        _print("This settlement still has a placeholder URL. Replace official_url before applying.")
        return 1

    if is_expired(settlement) and not args.allow_expired:
        _print("This settlement is expired. Re-run with --allow-expired to proceed anyway.")
        return 1

    try:
        profile = load_profile()
    except Exception as exc:
        _print(str(exc))
        return 1

    result = run_assisted_application(
        settlement,
        profile,
        headless=args.headless,
        slow_mo=args.slow_mo,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        no_submit=args.no_submit,
        manual_only=manual_only,
    )
    settlement["status"] = result.status
    if result.confirmation_number:
        settlement["confirmation_number"] = result.confirmation_number
    if result.fill_report.screenshot_path:
        settlement["confirmation_file"] = result.fill_report.screenshot_path
    append_history(settlement, result.message or f"Browser flow completed with status {result.status}.")
    save_settlements(settlements)
    _print(f"Updated {args.id}: {result.status}.")
    return 0 if result.status != "error" else 1


def _require_settlement(settlements: list[dict[str, Any]], settlement_id: str) -> dict[str, Any]:
    settlement = find_settlement(settlements, settlement_id)
    if not settlement:
        raise SystemExit(f"No settlement found with id {settlement_id}.")
    return settlement


def _safe_days_remaining(settlement: dict[str, Any]) -> int | None:
    try:
        return days_remaining(settlement, date.today())
    except Exception:
        return None


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


def _required_prompt(label: str) -> str:
    while True:
        value = _prompt(label)
        if value:
            return value
        print("Required.")


def _prompt_valid_url(label: str) -> str:
    while True:
        value = _required_prompt(label)
        if validate_url(value):
            return value
        print("Enter a valid http(s) URL.")


def _prompt_valid_date(label: str) -> str:
    while True:
        value = _required_prompt(label)
        try:
            parse_date(value)
            return value
        except ValueError:
            print("Enter a date as YYYY-MM-DD.")


def _prompt_bool(label: str) -> bool:
    while True:
        value = input(f"{label} [yes/no]: ").strip().lower()
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def _prompt_setup_value(label: str, existing: str, *, required: bool) -> str:
    while True:
        suffix = f" [{existing}]" if existing else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and existing:
            return existing
        if value or not required:
            return value
        print("Required for setup.")


def _yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _print(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def _status_from_hint(value: str) -> str:
    hint = value.strip().lower()
    if hint == "check_notice":
        return "needs_notice_id"
    if hint in {"needs_review", "check_phone_or_notice", "unlikely"}:
        return "needs_review"
    if hint in STATUSES:
        return hint
    return "todo"


def _csv_truthy(value: str) -> bool:
    text = value.strip().lower()
    if not text or text in {"no", "unknown", "n/a"}:
        return False
    return any(token in text for token in ("yes", "likely", "possibly", "validation", "required", "phone-number match"))


def _csv_notes(row: dict[str, str]) -> str:
    parts = []
    for field in ("category", "geography_relevance", "priority_for_brahm", "automation_notes", "source_note"):
        value = (row.get(field) or "").strip()
        if value:
            parts.append(f"{field}: {value}")
    if not (row.get("official_or_info_url") or "").strip():
        parts.append("official_url_missing: Find and verify the official settlement claim site before applying.")
    return "\n".join(parts)


def _default_questions_for_row(row: dict[str, str]) -> list[dict[str, str]]:
    questions = [
        {
            "id": "personally_matches_class",
            "question": "Based on the official settlement notice, do you personally match the class definition?",
            "type": "yes_no",
        },
        {
            "id": "eligibility_notes",
            "question": "Record the facts you verified locally, without guessing.",
            "type": "text",
        },
    ]
    if _csv_truthy(row.get("requires_notice_id", "")):
        questions.extend(
            [
                {
                    "id": "has_notice_id",
                    "question": "Did you receive a notice ID or claim ID?",
                    "type": "yes_no",
                },
                {
                    "id": "notice_id",
                    "question": "Enter notice ID if available.",
                    "type": "secret_or_text",
                },
            ]
        )
    if _csv_truthy(row.get("requires_proof", "")):
        questions.append(
            {
                "id": "has_proof",
                "question": "Do you have the proof or records required by the official claim form?",
                "type": "yes_no",
            }
        )
    if _csv_truthy(row.get("requires_login_or_validation", "")):
        questions.append(
            {
                "id": "login_completed",
                "question": "Have you completed any required account, notice, phone, or email validation?",
                "type": "yes_no",
            }
        )
    return questions


if __name__ == "__main__":
    sys.exit(main())
