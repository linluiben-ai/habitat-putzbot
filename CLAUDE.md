# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Putzbot" — a scheduled bot that runs the cleaning-crew ("Putzplan") lottery for a club (das-habitat.de). It reads member and cleaning-schedule data from two linked Notion data sources, draws members to fill upcoming weeks' crews, writes the result back to Notion, and notifies people via Slack. It runs unattended via GitHub Actions (`.github/workflows/monday_cleanup.yml`) on a cron (Mondays 08:00 UTC) or manually via `workflow_dispatch`.

The year is divided into **13 cycles of 4 weeks** (cycle 1 = KW 1–4, … cycle 13 = KW 49–52; in 53-week ISO years KW 53 joins cycle 13). Every Monday the bot posts a reminder for the current week; in the **last week of a cycle** it additionally plans the whole *next* cycle — creating pages and drawing crews four weeks in advance so people can plan around it.

[roadmap.md](roadmap.md) is the design doc for the full target state; [implementation-plan.md](implementation-plan.md) tracks which parts are built and records the agreed-upon decisions (candidate-pool rules, reschedule thresholds, verified Notion schemas). **Read implementation-plan.md before changing raffle or scheduling behavior** — it documents *why* the rules are what they are. The reschedule flow (Slack ✅/❌ reactions → webhook) is designed but not yet implemented; see [webhook-setup.md](webhook-setup.md).

## Commands

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
```

Run the bot (requires the env vars below):
```bash
python main.py
```

Run the offline test suite — no credentials or network needed, also runs in CI:
```bash
python tests.py
```

There is no test framework; `tests.py` is a plain script that fakes the Notion/Slack layer and exits non-zero on failure. It covers what is painful to test live: year boundaries, 53-week years, exhausted candidate pools, and double-booking within a cycle. Add cases there rather than writing throwaway scripts.

`test_pm.py` and `test_lostopf.py` are old git-ignored scratch files; `test_lostopf.py` is a stale copy of pre-V3 pool logic and should not be used as a reference.

## Environment variables

| Variable | Purpose |
|---|---|
| `NOTION_TOKEN` | Notion integration token |
| `SLACK_TOKEN` | Slack bot token |
| `DS_A_ID` | Notion data source: Mitgliederliste |
| `DS_B_ID` | Notion data source: Putzplan |
| `SLACK_CHANNEL_ID` | Channel for reminders and cycle summaries |
| `TEMPLATE_ID` | Notion page template for a new week's page |
| `DRY_RUN` | `"true"` → run the whole flow but skip every Notion/Slack write |
| `DEBUG` | `"true"` → verbose diagnostics (per-tier candidate counts, lookups) |
| `FORCE_PLAN` | `"true"` → run cycle planning even outside the last week of a cycle |
| `SLACK_TEST_USER_ID` | If set, **all** DMs are redirected to this user (sandbox testing — see [sandbox-setup.md](sandbox-setup.md)) |
| `USE_TEST_DATA` | `"true"` → use the Notion test copies instead of production |
| `TEST_DS_B_ID`, `TEST_TEMPLATE_ID` | Required when `USE_TEST_DATA=true`; config aborts rather than silently falling back to production |
| `TEST_DS_A_ID` | Optional — the Mitgliederliste is only ever read, so the real one is fine for tests |
| `PUTZPLAN_RELATION_PROP` | Name of the Mitgliederliste→Putzplan relation (default `Putzplan`). A duplicated Putzplan adds a *second* relation property; point this at it when testing. |

In production these come from GitHub Actions secrets. Locally, copy [.env.example](.env.example) to `.env` — `config.py` loads it via a small built-in parser (no dependency). Real environment variables always win over the file, so CI is unaffected.

## Module layout

| File | Responsibility |
|---|---|
| [main.py](main.py) | Entrypoint. Orchestration only — decides reminder vs. reminder + planning. |
| [config.py](config.py) | Env vars, Slack client, Notion headers, and **all tunable rules** as constants. |
| [cycles.py](cycles.py) | Pure date math: cycle ↔ week mapping, year boundaries, week distances. No I/O. |
| [notion.py](notion.py) | Every Notion call: paginated queries, week lookup, member loading, writes. |
| [raffle.py](raffle.py) | Candidate-pool tiers and the draw itself. |
| [slack_utils.py](slack_utils.py) | User lookup, sending, and all message texts. |
| [scheduler.py](scheduler.py) | The two scheduled processes: `remind_current_week` and `plan_next_cycle`. |

`cycles.py` is separate from `scheduler.py` because both `raffle.py` and `scheduler.py` need week math; folding it in would create an import cycle.

`DRY_RUN` is enforced *inside* the write functions in `notion.py`/`slack_utils.py`, so callers never check it. Any new write must respect this, or dry runs silently stop being safe.

## How the draw works

Eligibility is filtered in the Notion query itself (`notion.MEMBER_FILTER`): active membership status, onboarding done, and `Putzstatus` either empty or `Normal`. `Ausgetragen`, `Neu`, `Priorität` and `Postponed` are all excluded. (The V2 "❓ page icon" check is gone — `Putzstatus` replaced it.)

`raffle.select_crew` then walks a ladder of tiers from strict to loose:

```
≤1 Einsätze + Schonfrist → ≤1 Einsätze → ≤2 + Schonfrist → ≤2 → ≤3 + Schonfrist → ≤3
```

Two rules that are easy to break by accident:

1. **Locking.** If a tier has fewer candidates than open slots, *all* of them are locked in and only the remaining slots fall through to the looser tier. Someone who qualified under strict criteria must not lose their spot because the criteria were relaxed afterwards.
2. **`ist_zu_dicht_dran` is a hard block.** The soft "Schonfrist" (`RECENCY_WEEKS`, 12) is relaxable by design; the minimum gap between two assignments (`MIN_WEEKS_BETWEEN`, 4) is *not*, and applies on every tier. Without it the relaxed tiers happily draw someone for two weeks of the same cycle. There is a regression test for this.

The 2-new/2-old mix (`ist_neu` = joined less than a year ago) is the weakest criterion and only applies when sampling within the final tier, counting members already on the page.

`enrich_members` must be re-run per target week — distances are relative to the week being planned. Crews drawn earlier in the same run are tracked in `member["extra_weeks"]`, because the Notion relation is stale until the run finishes.

## Working notes

- Notion API version `2025-09-03`: `data_source_id` (not `database_id`) as the parent when creating pages, and `/v1/data_sources/{id}/query` for queries. When `template` is used in a page-creation payload, `children` must **not** be present.
- The Putzplan data source needs a **`Jahr` (number)** property. `Kalenderwoche` alone is ambiguous across years, which breaks recency ordering and cross-new-year planning. Pages without `Jahr` are skipped with a warning.
- Weeks with `Status: Nicht auswählen` or `Archiv: true` are never touched.
- The Putzplan database contains **sentinel pages that are not weeks** — "Ausgetragen" (KW 0) and "Postponed" (KW 54), a pre-`Putzstatus` workaround for parking members. `get_week_pages` drops any page whose KW is outside `1..iso_weeks_in_year`, and `putz_count` counts only *resolvable* pages, so these never count as a cleaning shift. Without that guard `week_index` clamps them to KW 53 and everyone parked there looks freshly cleaned. The pages are slated for deletion, but the guard should stay — it also protects against any future non-week page.
- The bot **only ever writes to the Putzplan** data source; the Mitgliederliste is read-only. That is why test setups only need a Putzplan copy. Beware: writing the `Mitglieder` relation makes Notion write the inverse relation onto member pages, so a test Putzplan pointing at the real Mitgliederliste must use a one-way relation.
- User-facing strings, print output, and Notion/Slack property names are German — keep new code consistent rather than mixing in English property names.
- Notion relations return at most 25 items inline; `_relation_ids` logs a debug warning when there are more.
- `venv/` and `.venv/` are both gitignored; either may be present locally.
