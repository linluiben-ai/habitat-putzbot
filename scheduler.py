"""Die zeitgesteuerten Prozesse: Plan (alle 4 Wochen) und Remind (wöchentlich)."""

import cycles
import notion
import raffle
import slack_utils
from config import (
    CREW_SIZE,
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


def crew_from_ids(member_ids, lookup):
    """Mitglieder-Dicts zu Relations-IDs, unbekannte IDs werden übersprungen."""
    return [lookup[mid] for mid in member_ids if mid in lookup]


def status_fuer(anzahl):
    """Welchen Notion-Status soll eine Woche mit so vielen Leuten haben?"""
    return WEEK_STATUS_FULL if anzahl >= CREW_SIZE else WEEK_STATUS_PLANNED


def setze_status(week, anzahl):
    """Status nachziehen, aber 'Erledigt'/'Nicht auswählen' nicht überschreiben."""
    if week["status"] in (None, WEEK_STATUS_PLANNED, WEEK_STATUS_FULL):
        notion.set_week_status(week["page_id"], status_fuer(anzahl))


def cache_week(week_pages, entry):
    """Lokalen Wochen-Cache nachziehen, damit spätere Schritte im selben Lauf
    nicht mit veralteten Belegungen weiterrechnen."""
    week_pages["by_week"][(entry["kw"], entry["year"])] = entry
    if entry.get("page_id"):
        week_pages["by_page_id"][entry["page_id"]] = entry
    return entry


def fill_week(week, members, week_pages, lookup, exclude_ids=()):
    """Eine Woche auffüllen: auslosen, nach Notion schreiben, DMs verschicken.

    Gemeinsam genutzt von der Zyklusplanung und vom Nachlosen nach einem
    Tausch. Gibt (crew, page_url, selected) zurück.
    """
    needed = CREW_SIZE - week["member_count"]

    # Abstände hängen von der Zielwoche ab -> pro Woche neu berechnen
    raffle.enrich_members(members, week_pages, week["kw"], week["year"])
    selected = raffle.select_crew(members, week, needed, exclude_ids=exclude_ids)

    if selected:
        print(f"   🎲 Ausgelost: {', '.join(m['name'] for m in selected)}")
    elif needed > 0:
        print("   ⚠️ Niemand ausgelost.")
    else:
        print("   ✅ Crew ist schon vollzählig.")

    all_ids = week["member_ids"] + [m["id"] for m in selected]
    page_url = week["page_url"]

    if week["page_status"] == "exists":
        if selected:
            notion.update_page_members(week["page_id"], all_ids)
            setze_status(week, len(all_ids))
            cache_week(week_pages, dict(week, member_ids=all_ids,
                                        member_count=len(all_ids),
                                        status=status_fuer(len(all_ids))))
    else:
        new_id, new_url = notion.create_week_page(
            week["kw"], week["year"], all_ids, status=status_fuer(len(all_ids))
        )
        page_url = new_url
        if new_id:
            cache_week(week_pages, {
                "page_id": new_id, "page_url": new_url,
                "kw": week["kw"], "year": week["year"],
                "member_ids": all_ids, "member_count": len(all_ids),
                "status": status_fuer(len(all_ids)), "archiv": False,
            })

    # Damit spätere Wochen im selben Lauf wissen, dass diese Leute verplant sind
    for member in selected:
        member["extra_weeks"].append((week["kw"], week["year"]))

    for member in selected:
        slack_utils.send_dm(
            member,
            slack_utils.build_draw_dm(member, week["kw"], page_url),
            metadata=slack_utils.auslosung_metadata(member, week["kw"], week["year"]),
        )

    crew = crew_from_ids(week["member_ids"], lookup) + selected
    return crew, page_url, selected


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

    crew = crew_from_ids(week["member_ids"], lookup)
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

        print(f"   Bereits eingetragen: {week['member_count']} — "
              f"benötigt: {max(0, CREW_SIZE - week['member_count'])}")

        raffle.enrich_members(members, week_pages, week_kw, week_year)
        for line in raffle.describe_candidates(members, week):
            debug(line.strip())

        crew, page_url, _ = fill_week(week, members, week_pages, lookup)
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
