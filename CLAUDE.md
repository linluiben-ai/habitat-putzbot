# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Putzbot" — a scheduled bot that runs the weekly cleaning-crew ("Putzplan") lottery for a club (das-habitat.de). It reads member and cleaning-schedule data from two linked Notion data sources, randomly draws members to fill the current week's crew, writes the result back to Notion, and posts a summary to Slack. It runs unattended via GitHub Actions (`.github/workflows/monday_cleanup.yml`), triggered on a cron (Mondays 08:00 UTC) or manually via `workflow_dispatch`.

All logic lives in [main.py](main.py); there is no package structure, framework, or build step.

## Commands

Setup (Windows, `venv/` is the local convention used in this repo):
```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
```

Run the bot locally (requires env vars below):
```bash
python main.py
```

Dry run (loads and prints the qualified candidate pool, makes no Notion/Slack writes):
```bash
DRY_RUN=true python main.py
```

There is no formal test suite. `test_pm.py` and `test_lostopf.py` are standalone manual-check scripts (git-ignored, not run in CI) — `test_pm.py` sends a real Slack DM to verify token/lookup wiring, `test_lostopf.py` is a scratch copy of the candidate-pool logic from `main.py`. Run them directly with `python test_pm.py` if needed; don't treat them as an automated suite.

## Required environment variables

| Variable | Purpose |
|---|---|
| `NOTION_TOKEN` | Notion integration token |
| `SLACK_TOKEN` | Slack bot token |
| `DS_A_ID` | Notion data source ID: Mitglieder (members) |
| `DS_B_ID` | Notion data source ID: Putzliste (cleaning schedule) |
| `SLACK_CHANNEL_ID` | Slack channel to post the weekly summary to |
| `TEMPLATE_ID` | Notion page template ID used to create a new week's page |
| `DRY_RUN` | `"true"` to only print the candidate pool and skip all writes |

In production these are injected as GitHub Actions secrets (see the workflow file). Locally, set them in the shell or an untracked `.env`-style mechanism — there's no `.env` loader in the code, so export them directly.

## Architecture / flow (in `main.py::main`)

1. **Check current week** (`get_current_week_status`) — queries data source B (Putzliste) for a page matching the current ISO calendar week. Counts existing members via the `Anzahl Mitglieder` rollup, falling back to counting the `Mitglieder` relation directly if the rollup reads 0.
2. **Load candidate pool** — queries data source A (Mitglieder) filtered to active, onboarded, non-passive members (see the Notion filter in `main()` for the exact status logic). For each member it resolves an email (prefers the `Interne Email` property, else derives `vorname.nachname@das-habitat.de` from the title via `clean_string`, which strips German umlauts/ß and diacritics). A member qualifies as a candidate if: not marked with a "❓" page icon, has an empty `Putzplan` relation (hasn't cleaned yet this cycle), and isn't already on this week's page.
3. **Draw and write** — if the week needs more people (target crew size is 4), samples the shortfall from the candidate pool via `random.sample` and either `update_existing_page` (relation patch) or `create_page_from_template` (new page from `TEMPLATE_ID`, properties `Titel`/`Mitglieder`/`Kalenderwoche` override the template — note `children` must NOT be included in the payload when `template` is used, per the Notion API).
4. **Notify Slack** — resolves each selected member's Slack user ID from their email (`get_slack_user_id`), builds a message tagging existing + newly-drawn members with a link back to the Notion page, and posts it via `chat_postMessage`.

`structure.md` describes a more elaborate target design (multi-week cycle planning, reschedule flow via emoji reactions, per-member reminder DMs) that is **not yet implemented** — `main.py` currently only implements the single-week `Raffle` step described there. Treat `structure.md` as a design doc/roadmap, not a description of current behavior.

## Working notes

- Uses the Notion API version `2025-09-03`, which requires `data_source_id` (not `database_id`) as the parent when creating pages, and `/v1/data_sources/{id}/query` (not `/v1/databases/{id}/query`) for queries.
- User-facing strings, print statements, and Notion/Slack property names are in German — keep new code consistent with this rather than mixing in English property names.
- `venv/` and `.venv/` are both gitignored; either may be present locally, pick one.
