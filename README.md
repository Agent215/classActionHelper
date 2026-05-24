# class-action-helper

`class-action-helper` is a local-only command-line tool for tracking class action settlements you may personally qualify for and assisting with claim form prefill in a real browser.

It does not decide that you qualify, invent claim facts, create supporting documents, bypass CAPTCHA, run a server, deploy anything, or store data in a cloud database. You are responsible for making truthful claims and reviewing every certification, declaration, and penalty-of-perjury statement before any submission attempt.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
install -m 755 scripts/claimBot ~/.local/bin/claimBot
install -m 755 scripts/claimbot ~/.local/bin/claimbot
```

If this Codex workspace has a read-only `.git` mountpoint, the repo uses `.git-local`
for Git metadata. Install the narrow wrapper to make normal `git` commands work in
this project:

```bash
install -m 755 scripts/git ~/.local/bin/git
```

## Private Profile

Run first-time setup:

```bash
claimbot setup
```

This prompts for your private profile values and saves them in `.env`, which is
ignored by git. You can also create the file without prompts:

```bash
claimbot init-profile
```

Supported fields:

```dotenv
FIRST_NAME=
LAST_NAME=
EMAIL=
PHONE=
ADDRESS1=
ADDRESS2=
CITY=Philadelphia
STATE=PA
ZIP=
COUNTRY=United States
PAYMENT_PREFERENCE=
PAYPAL_EMAIL=
VENMO=
ZELLE_EMAIL_OR_PHONE=
```

## Common Commands

```bash
claimbot
claimbot --help
claimbot setup
claimbot list
claimbot work
claimbot work --bulk --limit 3
claimbot auto-submit --bulk --limit 3
claimbot research --provider codex --output candidate-settlements.csv
claimbot unseed
```

After installing the local launcher, `claimbot` is equivalent to
`python claim_assistant.py` and can be run from any directory. The mixed-case
`claimBot` alias is also installed.

Running `claimbot` with no arguments opens the TUI by default. `claimbot tui`
does the same thing explicitly.

`claimbot tui` opens a menu-driven terminal UI for dashboard review, queue work,
eligibility, manual submit, apply, auto-submit, Codex research, mark, import,
validate, export, and unseed/reset.

`manual-submit` opens the browser and helps prefill fields, but it never attempts final submission. After you submit manually, it asks for a confirmation number and updates `settlements.yaml`.

`apply` also opens the browser and prefills fields, then saves a pre-review screenshot and prints a final review summary. It will only attempt one final submit if you type `REVIEWED` and then exactly `SUBMIT <settlement-id>`. If a certification checkbox is detected, it also requires exactly `CERTIFY <settlement-id>` before checking it.

If the tool cannot confidently identify the submit button, sees a CAPTCHA/bot check, finds unresolved notice/proof/login requirements, or lacks saved eligibility answers, it stops and marks the claim for manual action.

## Work Queue

Use `work` to automate the next safe step without choosing IDs manually:

```bash
claimbot work
claimbot work --mode eligibility
claimbot work --bulk --limit 3
claimbot work --id toms-of-maine-toothpaste
```

The queue sorts by deadline, asks eligibility questions when answers are missing,
and opens the browser only when the settlement is marked `eligible` or
`ready_for_review`. Bulk mode is sequential and still stops for eligibility,
manual review, CAPTCHA, proof, notice IDs, login, ambiguity, and confirmation
tracking.

`claimbot work --mode apply` may attempt final submit, but each claim still
requires `REVIEWED` and exactly `SUBMIT <settlement-id>` inside that session.

## Auto Submit No-Evidence Claims

Use `auto-submit` only for claims that are already marked eligible, have saved
eligibility answers, and require only profile information:

```bash
claimbot auto-submit --id toms-of-maine-toothpaste
claimbot auto-submit --bulk --limit 3
```

The command shows the exact queued claim IDs and requires a typed batch approval
phrase such as `AUTO SUBMIT id-one id-two`. It automatically skips claims that
require proof, notice ID, login, configured CAPTCHA/bot checks, missing eligibility
answers, placeholder URLs, or non-eligible statuses. At runtime it stops each claim
for manual action if the page shows CAPTCHA, certification text, ambiguous submit
buttons, or any unresolved requirement.

For a safe preview:

```bash
claimbot auto-submit --bulk --limit 3 --dry-run
```

## Data Files

- `settlements.yaml`: local settlement tracking, eligibility answers, statuses, history, and confirmation metadata.
- `.env`: private local profile, ignored by git.
- `browser-profile/`: persistent Chromium profile for local cookies/session, ignored by git.
- `screenshots/`: pre-review and post-submit screenshots, ignored by git.
- `confirmations/`: reserved for local confirmation files, ignored by git.
- `settlements-export.csv`: default local CSV export path.
- `research-prompts/`: generated AI research prompts, ignored by git.
- `candidate-settlements*.csv`: generated candidate CSVs, ignored by git.
- `backups/`: local tracker backups from `unseed`, ignored by git.

## Add A Settlement

For first-run setup, use:

```bash
claimbot setup
```

This prompts for the private profile values needed for form prefill, saves them to `.env`, creates local runtime directories, optionally imports a tracker CSV, and runs validation.

Run:

```bash
claimbot add
```

Then edit `settlements.yaml` to add settlement-specific eligibility questions and any explicit `form_strategy` selectors. Use only official settlement sites and your own truthful answers.

## Import A Tracker CSV

If you have a CSV with candidate settlements, import it locally:

```bash
claimbot import-csv /home/brahm/Downloads/possible_class_action_settlements_tracker.csv
```

Rows without an official URL are imported with `https://example.com/claim` and are blocked from `apply` or `manual-submit` until you replace `official_url` with a verified official claim site.

If the CSV includes `claim_form_url`, browser flows open that URL while still keeping
`official_url` for the settlement homepage and final review summary.

## Research Candidates With Codex

The first supported AI provider is Codex because this machine has the Codex CLI.
The command writes a prompt under `research-prompts/` and can run:

```bash
codex exec --search --cd /home/brahm/Dev/classActionBot ...
```

Generate a Codex-ready research prompt:

```bash
claimbot research --provider codex --output candidate-settlements.csv
```

Run Codex with web search and write candidate rows:

```bash
claimbot research --provider codex --output candidate-settlements.csv --run
```

After reviewing the CSV, import it:

```bash
claimbot import-csv candidate-settlements.csv
```

Or let the command import after a successful Codex run:

```bash
claimbot research --provider codex --output candidate-settlements.csv --run --import-after
```

Research output is treated as candidate data only. The prompt instructs Codex to
use live web research, prefer official settlement/admin/refund sources, avoid
guessing, and leave unknown cells blank or marked `unknown`.

To test discovery from a clean tracker:

```bash
claimbot unseed
claimbot research --provider codex --output candidate-settlements.csv --run --import-after
claimbot validate
claimbot list
```

## Reset Seed Data

Back up the current tracker and reset `settlements.yaml` to the placeholder seed:

```bash
claimbot unseed
```

Backups are written to `backups/`, which is ignored by git.

## GitHub SSH Remote

This project does not create HTTPS remotes. To add a GitHub remote later:

```bash
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```
