from __future__ import annotations

import argparse
from datetime import date
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .cli import (
    cmd_apply,
    cmd_auto_submit,
    cmd_eligibility,
    cmd_export,
    cmd_import_csv,
    cmd_manual_submit,
    cmd_mark,
    cmd_research,
    cmd_unseed,
    cmd_validate,
    cmd_work,
)
from .models import STATUSES, days_remaining, parse_date
from .storage import ensure_local_dirs, load_settlements


console = Console()

CLAIMBOT_BANNER = r"""
_________ .__         .__       __________        __
\_   ___ \|  | _____  |__| _____\______   \ _____/  |_
/    \  \/|  | \__  \ |  |/     \|    |  _//  _ \   __\
\     \___|  |__/ __ \|  |  Y Y  \    |   (  <_> )  |
 \______  /____(____  /__|__|_|  /______  /\____/|__|
        \/          \/         \/       \/
""".strip("\n")

CLAIMBOT_ART = r"""
                                      ∞×××××××××××××××××××××÷
                                      ××            ×××   ×××
                                       π××              ×××
                                         ×××           ××
                                           ×× ≠×××××××××
                                            ×××××××××××
                                            ××∞      ××
                                           ×××××××××××××
                                        =××            =×××
                                      ×××                 ×××
                                     ××        ××××        ×××
                                   ××≠        ≈×× ××××       ×××
                                 ∞××       ×××        ××∞     ×××
                                ××≠       ××π××× ≠×××  ××       ××π
                               ××         × ×× × ×× ××  ××       ×××
                              ××          ×× ×××π××  =××          ×××
                             ××            ×××   ∞××               ×××
                            ××               ××××   ×××             ×××
                           ××                  ×× ×××∞ ××            ××
                           ××             ×××× ×× ×  ××××            ×××
                           ××             ×∞×× ×× ×  ××≠×             ××
                           ××             ∞×∞≠××× ××× ×××             ××
                           ××               ××××  ×××××               ××
                            ××                 ×= ×∞                 ×××
                             ××                 ×××                 ≠××
                              ×××                                  ×××
                                ××××                             ××××
                                   ××××××≈                   ≠×××××
                                       =×××××××××××××××××××××××
""".strip("\n")


def run_tui() -> int:
    ensure_local_dirs()
    first_render = True
    try:
        while True:
            settlements = load_settlements()
            _render_dashboard(settlements, animate=first_render and sys.stdin.isatty())
            first_render = False
            choice = Prompt.ask(
                "Choose",
                choices=["w", "b", "e", "m", "a", "s", "r", "u", "k", "i", "v", "x", "q"],
                default="w",
                show_choices=False,
            ).lower()

            if choice == "q":
                return 0
            if choice == "w":
                _work_next()
            elif choice == "b":
                _bulk_work()
            elif choice == "e":
                _eligibility()
            elif choice == "m":
                _manual_submit()
            elif choice == "a":
                _apply()
            elif choice == "s":
                _auto_submit()
            elif choice == "r":
                _research()
            elif choice == "u":
                _unseed()
            elif choice == "k":
                _mark()
            elif choice == "i":
                _import_csv()
            elif choice == "v":
                cmd_validate(argparse.Namespace())
            elif choice == "x":
                _export()
            _pause()
    except KeyboardInterrupt:
        console.print("\nExiting.")
        return 130


def _render_dashboard(settlements: list[dict[str, Any]], *, animate: bool = False) -> None:
    console.clear()
    total = len(settlements)
    submitted = sum(1 for item in settlements if item.get("status") == "submitted")
    actionable = sum(1 for item in settlements if item.get("status") not in {"submitted", "skipped", "not_eligible", "error"})
    due_soon = sum(1 for item in settlements if _days(item) is not None and 0 <= _days(item) <= 14)
    header = f"Settlements: {total} | Actionable: {actionable} | Submitted: {submitted} | Due in 14 days: {due_soon}"
    console.print(f"[bold green]{CLAIMBOT_BANNER}[/bold green]")
    console.print(f"[green]{CLAIMBOT_ART}[/green]")
    if animate:
        time.sleep(0.25)
    console.print(Panel(header, title="claimbot", subtitle="w work | b bulk | e eligibility | m manual | a apply | s auto | r research | u unseed | k mark | i import | v validate | x export | q quit"))
    if animate:
        time.sleep(0.15)

    table = Table(title="Next Settlements By Deadline")
    for column in ("ID", "Status", "Deadline", "Days", "Proof", "Notice", "Name"):
        table.add_column(column)

    next_settlements = _sorted_settlements(settlements)[:15]
    if animate:
        with Live(_build_table([]), console=console, refresh_per_second=30) as live:
            for index in range(1, len(next_settlements) + 1):
                live.update(_build_table(next_settlements[:index]))
                time.sleep(0.035)
        return

    console.print(_build_table(next_settlements))


def _build_table(settlements: list[dict[str, Any]]) -> Table:
    table = Table(title="Next Settlements By Deadline")
    for column in ("ID", "Status", "Deadline", "Days", "Proof", "Notice", "Name"):
        table.add_column(column)

    for settlement in settlements:
        days = _days(settlement)
        style = "red" if days is not None and days < 0 else "yellow" if days is not None and days <= 14 else ""
        table.add_row(
            str(settlement.get("id", "")),
            str(settlement.get("status", "")),
            str(settlement.get("deadline", "")),
            "?" if days is None else str(days),
            _yes_no(settlement.get("requires_proof")),
            _yes_no(settlement.get("requires_notice_id")),
            str(settlement.get("name", "")),
            style=style,
        )
    return table


def _work_next() -> None:
    cmd_work(_browser_args(id=None, bulk=False, limit=1, mode="manual-submit"))


def _bulk_work() -> None:
    limit = IntPrompt.ask("Maximum settlements to work", default=3)
    mode = Prompt.ask("Mode", choices=["eligibility", "manual-submit", "apply"], default="manual-submit")
    include_blocked = Confirm.ask("Include notice/proof/login blocked items?", default=False)
    if mode == "apply":
        console.print("[bold yellow]Auto submit mode still requires per-claim REVIEWED and exact SUBMIT <id> approval.[/bold yellow]")
        if not Confirm.ask("Continue with apply mode?", default=False):
            return
    cmd_work(_browser_args(id=None, bulk=True, limit=limit, mode=mode, include_blocked=include_blocked))


def _eligibility() -> None:
    settlement_id = _ask_id()
    if settlement_id:
        cmd_eligibility(argparse.Namespace(id=settlement_id))


def _manual_submit() -> None:
    settlement_id = _ask_id()
    if settlement_id:
        cmd_manual_submit(_browser_args(id=settlement_id))


def _apply() -> None:
    settlement_id = _ask_id()
    if not settlement_id:
        return
    console.print("[bold yellow]Apply may attempt final submit only after REVIEWED and exact SUBMIT approval.[/bold yellow]")
    if Confirm.ask("Open apply flow?", default=False):
        cmd_apply(_browser_args(id=settlement_id))


def _auto_submit() -> None:
    console.print("[bold yellow]Auto-submit mode is limited to eligible no-evidence claims and still requires a typed batch approval phrase.[/bold yellow]")
    if not Confirm.ask("Open auto-submit mode?", default=False):
        return
    bulk = Confirm.ask("Bulk auto-submit?", default=True)
    limit = IntPrompt.ask("Maximum settlements", default=3) if bulk else 1
    settlement_id = "" if bulk else _ask_id()
    cmd_auto_submit(_browser_args(id=settlement_id or None, bulk=bulk, limit=limit, mode="manual-submit"))


def _research() -> None:
    console.print("[bold yellow]Research creates candidate rows only. Review sources before applying.[/bold yellow]")
    output = Prompt.ask("Candidate CSV output", default="candidate-settlements.csv")
    geography = Prompt.ask("Geography", default="Pennsylvania and nationwide U.S.")
    categories = Prompt.ask(
        "Categories",
        default="consumer products, privacy, data breach, subscriptions, ecommerce fees, TCPA/robocalls",
    )
    limit = IntPrompt.ask("Maximum candidates", default=25)
    run = Confirm.ask("Run Codex now with web search?", default=False)
    import_after = Confirm.ask("Import CSV after successful run?", default=False) if run else False
    cmd_research(
        argparse.Namespace(
            provider="codex",
            output=output,
            geography=geography,
            categories=categories,
            days_ahead=180,
            limit=limit,
            run=run,
            import_after=import_after,
        )
    )


def _unseed() -> None:
    console.print("[bold yellow]This backs up settlements.yaml, then resets it to the placeholder seed.[/bold yellow]")
    if Confirm.ask("Unseed current settlement data?", default=False):
        cmd_unseed(argparse.Namespace(yes=True))


def _mark() -> None:
    settlement_id = _ask_id()
    if not settlement_id:
        return
    status = Prompt.ask("Status", choices=sorted(STATUSES))
    note = Prompt.ask("Optional note", default="")
    cmd_mark(argparse.Namespace(id=settlement_id, status=status, note=note))


def _import_csv() -> None:
    path = Prompt.ask("CSV path")
    if path:
        cmd_import_csv(argparse.Namespace(path=path))


def _export() -> None:
    output = Prompt.ask("Output CSV", default="settlements-export.csv")
    cmd_export(argparse.Namespace(output=output))


def _ask_id() -> str:
    return Prompt.ask("Settlement ID").strip()


def _browser_args(
    *,
    id: str | None,
    bulk: bool = False,
    limit: int = 1,
    mode: str = "manual-submit",
    include_blocked: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        id=id,
        bulk=bulk,
        limit=limit,
        mode=mode,
        include_blocked=include_blocked,
        allow_expired=False,
        headless=False,
        slow_mo=0,
        dry_run=False,
        no_submit=False,
        overwrite=False,
    )


def _sorted_settlements(settlements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(settlement: dict[str, Any]) -> tuple[date, str]:
        try:
            deadline = parse_date(settlement.get("deadline"))
        except Exception:
            deadline = date.max
        return deadline, str(settlement.get("id", ""))

    return sorted(settlements, key=key)


def _days(settlement: dict[str, Any]) -> int | None:
    try:
        return days_remaining(settlement)
    except Exception:
        return None


def _yes_no(value: Any) -> str:
    return "yes" if bool(value) else "no"


def _pause() -> None:
    Prompt.ask("Press Enter to return to the dashboard", default="")
