"""Putzbot — Einstiegspunkt.

Läuft wöchentlich (montags) via GitHub Actions und orchestriert nur:
jede Woche eine Erinnerung, in der letzten Woche eines Zyklus zusätzlich
die Planung des Folgezyklus. Die eigentliche Logik liegt in den Modulen.
"""

import sys

import cycles
import notion
import scheduler
from config import (
    DATENQUELLE,
    DEBUG,
    DRY_RUN,
    FORCE_PLAN,
    SLACK_TEST_USER_ID,
    SLACK_ZIEL,
    check_env,
)


def main():
    check_env()

    kw, year = cycles.current_week()
    cycle = cycles.cycle_of_week(kw)

    print(f"🤖 Putzbot — KW {kw}/{year} (Zyklus {cycle})")
    print(f"   Notion: {DATENQUELLE}   Slack: {SLACK_ZIEL}")
    if DRY_RUN:
        print("🧪 DRY RUN — keine Schreibzugriffe auf Notion oder Slack.")
    if DEBUG:
        print("🐛 DEBUG aktiv.")
    if FORCE_PLAN:
        print("⏩ FORCE_PLAN — Zyklusplanung läuft unabhängig vom Datum.")
    if SLACK_TEST_USER_ID:
        print(f"📮 Alle DMs gehen umgeleitet an {SLACK_TEST_USER_ID}.")

    week_pages = notion.get_week_pages()
    if week_pages is None:
        return 1

    all_members = notion.get_all_members()
    if all_members is None:
        return 1
    lookup = {member["id"]: member for member in all_members}

    scheduler.remind_current_week(week_pages, lookup, kw, year)

    if scheduler.should_plan(kw, year, force=FORCE_PLAN):
        members = notion.get_eligible_members()
        if members is None:
            return 1
        scheduler.plan_next_cycle(week_pages, members, lookup, kw, year)
    else:
        last_kw = cycles.weeks_in_cycle(cycle, year)[-1]
        print(f"\n💤 Kein Plan-Lauf — der läuft erst in KW {last_kw} (Ende Zyklus {cycle}).")

    print("\n✅ Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
