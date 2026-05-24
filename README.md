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

Create your ignored local profile:

```bash
python claim_assistant.py init-profile
```

This copies `.env.example` to `.env`. Fill in only your real personal information in `.env`; it is ignored by git.

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
claimBot --help
claimBot setup
claimBot list
python claim_assistant.py setup
python claim_assistant.py init-profile
python claim_assistant.py add
python claim_assistant.py import-csv /path/to/possible_class_action_settlements_tracker.csv
python claim_assistant.py validate
python claim_assistant.py list
python claim_assistant.py eligibility --id example-settlement
python claim_assistant.py apply --id example-settlement
python claim_assistant.py manual-submit --id example-settlement
python claim_assistant.py export
```

After installing the local launcher, `claimBot` is equivalent to `python claim_assistant.py` and can be run from any directory.

`manual-submit` opens the browser and helps prefill fields, but it never attempts final submission. After you submit manually, it asks for a confirmation number and updates `settlements.yaml`.

`apply` also opens the browser and prefills fields, then saves a pre-review screenshot and prints a final review summary. It will only attempt one final submit if you type `REVIEWED` and then exactly `SUBMIT <settlement-id>`. If a certification checkbox is detected, it also requires exactly `CERTIFY <settlement-id>` before checking it.

If the tool cannot confidently identify the submit button, sees a CAPTCHA/bot check, finds unresolved notice/proof/login requirements, or lacks saved eligibility answers, it stops and marks the claim for manual action.

## Data Files

- `settlements.yaml`: local settlement tracking, eligibility answers, statuses, history, and confirmation metadata.
- `.env`: private local profile, ignored by git.
- `browser-profile/`: persistent Chromium profile for local cookies/session, ignored by git.
- `screenshots/`: pre-review and post-submit screenshots, ignored by git.
- `confirmations/`: reserved for local confirmation files, ignored by git.
- `settlements-export.csv`: default local CSV export path.

## Add A Settlement

For first-run setup, use:

```bash
python claim_assistant.py setup
```

This prompts for the private profile values needed for form prefill, saves them to `.env`, creates local runtime directories, optionally imports a tracker CSV, and runs validation.

Run:

```bash
python claim_assistant.py add
```

Then edit `settlements.yaml` to add settlement-specific eligibility questions and any explicit `form_strategy` selectors. Use only official settlement sites and your own truthful answers.

## Import A Tracker CSV

If you have a CSV with candidate settlements, import it locally:

```bash
python claim_assistant.py import-csv /home/brahm/Downloads/possible_class_action_settlements_tracker.csv
```

Rows without an official URL are imported with `https://example.com/claim` and are blocked from `apply` or `manual-submit` until you replace `official_url` with a verified official claim site.

## GitHub SSH Remote

This project does not create HTTPS remotes. To add a GitHub remote later:

```bash
git remote add origin git@github.com:OWNER/REPO.git
git push -u origin main
```
