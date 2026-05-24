from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from .safety import SubmissionGuard, SubmitResult
from .storage import BROWSER_PROFILE_DIR, SCREENSHOTS_DIR, ensure_local_dirs


@dataclass
class FillReport:
    filled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    screenshot_path: str = ""


@dataclass
class BrowserRunResult:
    status: str
    fill_report: FillReport
    confirmation_number: str = ""
    message: str = ""


PROFILE_FIELD_PATTERNS = {
    "first_name": ["first name", "firstname", "first_name", "fname"],
    "last_name": ["last name", "lastname", "last_name", "lname"],
    "email": ["email", "e-mail"],
    "phone": ["phone", "telephone", "mobile"],
    "address1": ["address 1", "address line 1", "street address", "address1", "address_1"],
    "address2": ["address 2", "address line 2", "apt", "suite", "address2", "address_2"],
    "city": ["city", "town"],
    "state": ["state", "province"],
    "zip": ["zip", "zipcode", "postal code", "postal"],
    "country": ["country"],
    "payment_preference": ["payment preference", "payment method", "preferred payment"],
    "paypal_email": ["paypal", "paypal email"],
    "venmo": ["venmo"],
    "zelle_email_or_phone": ["zelle"],
}


def run_assisted_application(
    settlement: dict[str, Any],
    profile: dict[str, Any],
    *,
    headless: bool = False,
    slow_mo: int = 0,
    dry_run: bool = False,
    overwrite: bool = False,
    no_submit: bool = False,
    manual_only: bool = False,
) -> BrowserRunResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run pip install -r requirements.txt.") from exc

    ensure_local_dirs()
    fill_report = FillReport()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(BROWSER_PROFILE_DIR),
            headless=headless,
            slow_mo=slow_mo,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(str(settlement["official_url"]), wait_until="domcontentloaded", timeout=60000)
            print("Browser opened. If this is not the claim form, navigate to the form and press Enter.")
            input("Press Enter when the claim form is visible: ")

            if dry_run:
                fill_report.skipped.append("Dry run enabled; no fields were filled.")
            else:
                fill_report = prefill_profile(page, profile, settlement.get("form_strategy") or {}, overwrite=overwrite)

            fill_report.screenshot_path = save_screenshot(page, settlement["id"], "pre-review")
            print_review_summary(settlement, fill_report)

            if manual_only or no_submit:
                confirmation = input("After manual submission, enter confirmation number or type none: ").strip()
                return BrowserRunResult(
                    status="submitted" if confirmation.lower() != "none" and confirmation else "needs_manual_action",
                    fill_report=fill_report,
                    confirmation_number="" if confirmation.lower() == "none" else confirmation,
                    message="Manual submit flow completed.",
                )

            reviewed = input("Type REVIEWED to continue to submission options, or anything else to stop: ").strip()
            if reviewed != "REVIEWED":
                return BrowserRunResult("ready_for_review", fill_report, message="Stopped before submission.")

            certification_text = detect_certification_text(page)
            typed_certification = ""
            if certification_text:
                print("Certification or legal attestation detected:")
                print(certification_text)
                typed_certification = input(
                    f"Type CERTIFY {settlement['id']} if you personally certify this statement is true and want me to check it: "
                ).strip()
                if typed_certification == f"CERTIFY {settlement['id']}":
                    check_certification_box(page, certification_text)

            typed_submit = input(
                f"Do you want the tool to attempt final submission for this claim? Type SUBMIT {settlement['id']} to approve: "
            ).strip()
            captcha_detected = detect_captcha(page)
            guard = SubmissionGuard(settlement)
            decision = guard.evaluate(
                typed_submit,
                pre_submit_screenshot=fill_report.screenshot_path,
                captcha_detected=captcha_detected,
                certification_text=certification_text,
                typed_certification=typed_certification,
            )
            if not decision.allowed:
                for reason in decision.reasons:
                    print(f"Blocked: {reason}")
                return BrowserRunResult("needs_manual_action", fill_report, message="; ".join(decision.reasons))

            submit_result = attempt_submit(page, settlement["id"])
            if submit_result.screenshot_path:
                fill_report.screenshot_path = submit_result.screenshot_path
            if submit_result.result in {"submitted_confirmed", "submitted_uncertain"}:
                confirmation = input("Enter the confirmation number, or type none: ").strip()
                return BrowserRunResult(
                    status="submitted" if confirmation.lower() != "none" and confirmation else "needs_manual_action",
                    fill_report=fill_report,
                    confirmation_number="" if confirmation.lower() == "none" else confirmation,
                    message=submit_result.message,
                )
            return BrowserRunResult("needs_manual_action", fill_report, message=submit_result.message)
        except PlaywrightTimeoutError as exc:
            return BrowserRunResult("error", fill_report, message=f"Browser timeout: {exc}")
        except Exception as exc:
            return BrowserRunResult("error", fill_report, message=str(exc))
        finally:
            context.close()


def prefill_profile(page: Any, profile: dict[str, Any], form_strategy: dict[str, Any], *, overwrite: bool) -> FillReport:
    report = FillReport()
    explicit_fields = (form_strategy or {}).get("fields") or {}

    for field_name, value in profile.items():
        if value in (None, ""):
            report.skipped.append(f"{field_name}: profile value is blank.")
            continue

        explicit_selector = explicit_fields.get(field_name)
        if explicit_selector:
            filled = _fill_locator(page.locator(explicit_selector), str(value), overwrite)
            (report.filled if filled else report.skipped).append(
                f"{field_name}: {'filled configured selector' if filled else 'configured selector unavailable or non-empty'}."
            )
            continue

        patterns = PROFILE_FIELD_PATTERNS.get(field_name, [field_name])
        outcome = _fill_by_patterns(page, field_name, str(value), patterns, overwrite)
        (report.filled if outcome == "filled" else report.skipped).append(f"{field_name}: {outcome}.")

    return report


def save_screenshot(page: Any, settlement_id: str, phase: str) -> str:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = SCREENSHOTS_DIR / f"{settlement_id}-{phase}-{timestamp}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def print_review_summary(settlement: dict[str, Any], report: FillReport) -> None:
    print("\nFinal review summary")
    print(f"Settlement: {settlement.get('name')}")
    print(f"Official URL: {settlement.get('official_url')}")
    print(f"Deadline: {settlement.get('deadline')}")
    print(f"Eligibility summary: {settlement.get('eligibility_summary')}")
    print(f"Eligibility answers: {settlement.get('eligibility_answers') or {}}")
    print(f"Filled fields: {', '.join(report.filled) if report.filled else 'none'}")
    print(f"Skipped fields: {', '.join(report.skipped) if report.skipped else 'none'}")
    print(f"Pre-review screenshot: {report.screenshot_path}")

    warnings = []
    if settlement.get("requires_proof"):
        warnings.append("proof may be required")
    if settlement.get("requires_notice_id"):
        warnings.append("notice ID may be required")
    if settlement.get("requires_login"):
        warnings.append("login may be required")
    if settlement.get("has_captcha_or_bot_check"):
        warnings.append("CAPTCHA or bot check is configured")
    if warnings:
        print(f"Warnings: {', '.join(warnings)}")


def detect_captcha(page: Any) -> bool:
    patterns = ["captcha", "recaptcha", "hcaptcha", "bot check", "i am not a robot"]
    for pattern in patterns:
        try:
            if page.get_by_text(re.compile(pattern, re.IGNORECASE)).first.is_visible(timeout=500):
                return True
        except Exception:
            pass
    try:
        frames = page.locator("iframe[src*='captcha'], iframe[src*='recaptcha'], iframe[src*='hcaptcha']")
        return frames.count() > 0 and frames.first.is_visible(timeout=500)
    except Exception:
        return False


def detect_certification_text(page: Any) -> str:
    patterns = re.compile(r"(certif|declare|penalty of perjury|attest|affirm)", re.IGNORECASE)
    try:
        labels = page.locator("label").all()
        for label in labels:
            text = label.inner_text(timeout=500).strip()
            if text and patterns.search(text):
                return text
    except Exception:
        pass
    return ""


def check_certification_box(page: Any, certification_text: str) -> bool:
    try:
        label = page.get_by_text(certification_text, exact=True).first
        checkbox = label.locator("input[type='checkbox']").first
        if checkbox.count() and checkbox.is_visible():
            checkbox.check()
            return True
    except Exception:
        pass
    try:
        boxes = page.locator("input[type='checkbox']")
        if boxes.count() == 1 and boxes.first.is_visible():
            boxes.first.check()
            return True
    except Exception:
        pass
    return False


def attempt_submit(page: Any, settlement_id: str) -> SubmitResult:
    selectors = [
        "button:has-text('Submit Claim')",
        "button:has-text('File Claim')",
        "button:has-text('Submit')",
        "input[type='submit'][value='Submit Claim']",
        "input[type='submit'][value='File Claim']",
        "input[type='submit'][value='Submit']",
    ]
    matches = []
    for selector in selectors:
        try:
            locator = page.locator(selector)
            for index in range(locator.count()):
                item = locator.nth(index)
                if item.is_visible():
                    matches.append(item)
        except Exception:
            continue

    if len(matches) != 1:
        screenshot = save_screenshot(page, settlement_id, "submit-ambiguous")
        return SubmitResult("manual_required", "Could not confidently identify exactly one submit button.", screenshot_path=screenshot)

    matches[0].click()
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    screenshot = save_screenshot(page, settlement_id, "post-submit")
    return SubmitResult("submitted_uncertain", "Submit button clicked once; confirmation still requires your review.", screenshot_path=screenshot)


def _fill_by_patterns(page: Any, field_name: str, value: str, patterns: list[str], overwrite: bool) -> str:
    for pattern in patterns:
        locators = [
            lambda pattern=pattern: page.get_by_label(re.compile(pattern, re.IGNORECASE)),
            lambda pattern=pattern: page.get_by_placeholder(re.compile(pattern, re.IGNORECASE)),
            lambda pattern=pattern: page.locator(_attribute_selector(pattern, "name")),
            lambda pattern=pattern: page.locator(_attribute_selector(pattern, "id")),
            lambda pattern=pattern: page.locator(_attribute_selector(pattern, "aria-label")),
        ]
        for locator_factory in locators:
            try:
                if _fill_locator(locator_factory(), value, overwrite):
                    return "filled"
            except Exception:
                continue
    return "no confident visible match"


def _attribute_selector(pattern: str, attr: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "", pattern.lower())
    return f"input[{attr}*='{token}' i], textarea[{attr}*='{token}' i], select[{attr}*='{token}' i]"


def _fill_locator(locator: Any, value: str, overwrite: bool) -> bool:
    visible = []
    count = min(locator.count(), 10)
    for index in range(count):
        item = locator.nth(index)
        try:
            if item.is_visible():
                visible.append(item)
        except Exception:
            continue
    if len(visible) != 1:
        return False

    item = visible[0]
    try:
        current = item.input_value(timeout=500)
        if current and not overwrite:
            return False
    except Exception:
        current = ""

    try:
        tag = item.evaluate("element => element.tagName.toLowerCase()")
        if tag == "select":
            try:
                item.select_option(label=value)
            except Exception:
                item.select_option(value=value)
        else:
            item.fill(value)
        return True
    except Exception:
        return False

