"""Die zeitgesteuerten Prozesse: Plan (alle 4 Wochen) und Remind (wöchentlich)."""

import cycles
import notion
import raffle
import slack_utils
from config import (
    CREW_SIZE,
    DRY_RUN,
    WEEK_STATUS_BLOCKED,
    WEEK_STATUS_DONE,
    WEEK_STATUS_FULL,
    WEEK_STATUS_PLANNED,
    debug,
)


def _is_untouchable(week):
    """Archivierte und bewusst gesperrte Wochen fasst der Bot nicht an."""
    if week["archiv"]:
        return "archiviert"
    if week["status"] == WEEK_STATUS_BLOCKED:
        return f"Status '{WEEK_STATUS_BLOCKED}'"
    return None


def _crew_from_ids(member_ids, lookup):
    """Mitglieder-Dicts zu Relations-IDs, unbekannte IDs werden übersprungen."""
    return [lookup[mid] for mid in member_ids if mid in lookup]


def remind_current_week(week_pages, lookup, kw, year):
    """Wöchentliche Erinnerung: wer ist diese Woche dran."""
    print(f"\n📣 Erinnerung für KW {kw}/{year}")

    week = notion.notion_lookup(kw, year, week_pages)

    reason = _is_untouchable(week)
    if reason:
        print(f"   ⏭️ Übersprungen ({reason}).")
        return

    if week["page_status"] == "empty":
        print("   ⚠️ Für diese Woche existiert keine Notion-Seite — keine Erinnerung verschickt.")
        return

    crew = _crew_from_ids(week["member_ids"], lookup)
    slack_utils.post_channel(slack_utils.build_reminder(kw, crew, week["page_url"]))


def plan_next_cycle(week_pages, members, lookup, kw, year):
    """Für jede Woche des Folgezyklus Seite sicherstellen und ggf. auslosen."""
    cycle, target_year = cycles.next_cycle(kw, year)
    weeks = cycles.next_cycle_weeks(kw, year)

    print(f"\n🗓️ Plane Zyklus {cycle}/{target_year} — KW {', '.join(str(w) for w, _ in weeks)}")

    summary = []

    for week_kw, week_year in weeks:
        print(f"\n   ── KW {week_kw}/{week_year} ──")
        week = notion.notion_lookup(week_kw, week_year, week_pages)

        reason = _is_untouchable(week)
        if reason:
            print(f"   ⏭️ Übersprungen ({reason}).")
            continue

        if week["status"] == WEEK_STATUS_DONE:
            print("   ⏭️ Übersprungen (bereits erledigt).")
            continue

        needed = CREW_SIZE - week["member_count"]
        print(f"   Bereits eingetragen: {week['member_count']} — benötigt: {max(0, needed)}")

        # Abstände hängen von der Zielwoche ab -> pro Woche neu berechnen
        raffle.enrich_members(members, week_pages, week_kw, week_year)
        for line in raffle.describe_candidates(members, week):
            debug(line.strip())

        selected = raffle.select_crew(members, week, needed)

        if selected:
            print(f"   🎲 Ausgelost: {', '.join(m['name'] for m in selected)}")
        elif needed > 0:
            print("   ⚠️ Niemand ausgelost.")
        else:
            print("   ✅ Crew ist schon vollzählig.")

        all_ids = week["member_ids"] + [m["id"] for m in selected]
        final_status = WEEK_STATUS_FULL if len(all_ids) >= CREW_SIZE else WEEK_STATUS_PLANNED

        page_url = week["page_url"]

        if week["page_status"] == "exists":
            if selected:
                notion.update_page_members(week["page_id"], all_ids)
                if week["status"] in (None, WEEK_STATUS_PLANNED, WEEK_STATUS_FULL):
                    notion.set_week_status(week["page_id"], final_status)
        else:
            new_id, new_url = notion.create_week_page(
                week_kw, week_year, all_ids, status=final_status
            )
            page_url = new_url
            if new_id:
                # Lokalen Cache nachziehen, damit spätere Wochen den Stand kennen
                entry = {
                    "page_id": new_id,
                    "page_url": new_url,
                    "kw": week_kw,
                    "year": week_year,
                    "member_ids": all_ids,
                    "member_count": len(all_ids),
                    "status": final_status,
                    "archiv": False,
                }
                week_pages["by_week"][(week_kw, week_year)] = entry
                week_pages["by_page_id"][new_id] = entry

        # Damit die nächste Woche im Loop weiß, dass diese Leute schon verplant sind
        for member in selected:
            member["extra_weeks"].append((week_kw, week_year))

        for member in selected:
            slack_utils.send_dm(
                member, slack_utils.build_draw_dm(member, week_kw, page_url)
            )

        crew = _crew_from_ids(week["member_ids"], lookup) + selected
        summary.append((week_kw, crew, page_url))

    if summary:
        print()
        slack_utils.post_channel(slack_utils.build_cycle_summary(cycle, target_year, summary))

    return summary


def should_plan(kw, year, force=False):
    """Plan läuft in der letzten Woche eines Zyklus — oder erzwungen via FORCE_PLAN."""
    if force:
        debug("FORCE_PLAN gesetzt — Plan-Lauf wird erzwungen.")
        return True
    return cycles.is_last_week_of_cycle(kw, year)
