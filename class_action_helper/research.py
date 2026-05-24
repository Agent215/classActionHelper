from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import shutil
import subprocess

from .storage import ROOT


RESEARCH_PROMPTS_DIR = ROOT / "research-prompts"
DEFAULT_CANDIDATE_CSV = ROOT / "candidate-settlements.csv"

CANDIDATE_CSV_FIELDS = [
    "id",
    "name",
    "category",
    "official_or_info_url",
    "eligibility_summary",
    "geography_relevance",
    "deadline",
    "status_hint",
    "requires_notice_id",
    "requires_proof",
    "requires_login_or_validation",
    "expected_benefit",
    "priority_for_brahm",
    "automation_notes",
    "source_note",
    "claim_form_url",
    "source_url",
    "url_confidence",
    "url_verified_date",
]


@dataclass
class ResearchCommand:
    provider: str
    prompt_path: Path
    output_path: Path
    command: list[str]


def build_research_prompt(
    *,
    output_path: Path,
    geography: str,
    categories: str,
    days_ahead: int,
    limit: int,
) -> str:
    fields = ",".join(CANDIDATE_CSV_FIELDS)
    return f"""You are helping maintain a local personal class-action settlement tracker.

Task:
Find currently open or upcoming class action settlements and consumer refund programs that may be relevant to a person in {geography}. Focus on filing deadlines within the next {days_ahead} days where possible. Categories of interest: {categories}.

Hard requirements:
- Use live web research. Do not rely on model memory.
- Prefer official settlement websites, court-approved settlement administrator pages, FTC/state AG refund pages, or official claims portals.
- Do not invent eligibility, deadlines, URLs, benefits, proof requirements, notice IDs, or claim form URLs.
- If a value is unknown, leave the CSV cell blank or write "unknown"; do not guess.
- Include only candidates that appear to have an active claim/election/payment window or a clearly upcoming deadline.
- Do not include personal information.
- Treat all rows as candidates for later human verification.
- Write exactly {limit} rows or fewer.

Output:
Create or overwrite this CSV file:
{output_path}

The CSV must use exactly this header:
{fields}

Column guidance:
- id: stable lowercase slug.
- official_or_info_url: official settlement/refund homepage where possible.
- claim_form_url: direct claim/election/payment form URL only if found from the official site.
- source_url: page used to verify the URL/deadline.
- url_confidence: short note such as "official settlement homepage found; claim form linked from official site".
- url_verified_date: use {date.today().isoformat()}.
- status_hint: one of todo, needs_review, check_notice, check_phone_or_notice, unlikely.
- requires_notice_id/requires_proof/requires_login_or_validation: concise plain text such as yes/likely, no, unknown, possibly email validation.
- priority_for_brahm: high, medium, or low based on Pennsylvania/nationwide relevance, effort, deadline urgency, and likely benefit.
- automation_notes: include cautions such as CAPTCHA, notice required, proof likely, official URL missing, or manual review recommended.
- source_note: cite the source type in a short phrase, not a long quotation.

After writing the CSV, respond with a short summary of how many candidates were written and any important caveats. Do not print the CSV body in chat.
"""


def write_research_prompt(
    *,
    output_path: Path,
    geography: str,
    categories: str,
    days_ahead: int,
    limit: int,
) -> Path:
    RESEARCH_PROMPTS_DIR.mkdir(exist_ok=True)
    prompt_path = RESEARCH_PROMPTS_DIR / "codex-settlement-research.md"
    prompt = build_research_prompt(
        output_path=output_path,
        geography=geography,
        categories=categories,
        days_ahead=days_ahead,
        limit=limit,
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def build_research_command(provider: str, prompt_path: Path, output_path: Path) -> ResearchCommand:
    normalized = provider.lower()
    if normalized != "codex":
        raise ValueError("Only the codex provider is currently supported.")
    return ResearchCommand(
        provider="codex",
        prompt_path=prompt_path,
        output_path=output_path,
        command=[
            "codex",
            "--search",
            "exec",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(ROOT),
            prompt_path.read_text(encoding="utf-8"),
        ],
    )


def run_research_command(command: ResearchCommand) -> int:
    executable = shutil.which(command.command[0])
    if not executable:
        raise FileNotFoundError(f"{command.command[0]} was not found on PATH.")
    completed = subprocess.run(command.command, cwd=ROOT, check=False)
    return completed.returncode
