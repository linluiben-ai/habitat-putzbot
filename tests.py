"""Offline-Tests für die Zyklus- und Auslosungslogik.

Läuft ohne Notion/Slack und ohne Env-Variablen — Notion- und Slack-Aufrufe
werden gefaked. Aufruf:

    python tests.py

Deckt bewusst die Fälle ab, die sich in echt schlecht testen lassen:
Jahreswechsel, KW-53-Jahre, leergelaufene Kandidatenpools und die Frage,
ob jemand im selben Zyklus doppelt verplant wird.
"""

import sys
from collections import Counter
from datetime import date, timedelta

import config

config.DEBUG = False

import cycles  # noqa: E402
import notion  # noqa: E402
import raffle  # noqa: E402
import scheduler  # noqa: E402
import slack_utils  # noqa: E402

TODAY = date.today()
FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"  FEHLER {label}: ist {got!r}, erwartet {want!r}")
        print(f"  ✗ {label}")
    else:
        print(f"  ✓ {label}")


def member(mid, count=0, recent=False, new=False, too_close=False, putz_pages=()):
    """Mitglied mit schon berechneten Flags (umgeht enrich_members)."""
    abstand = 2 if too_close else (8 if recent else None)
    return {
        "id": mid,
        "name": f"Nachname{mid}, Vorname{mid}",
        "email": f"{mid}@das-habitat.de",
        "eintrittsdatum": (TODAY - timedelta(days=30 if new else 900)).isoformat(),
        "putzstatus": None,
        "putz_page_ids": list(putz_pages) + ["alt"] * count,
        "extra_weeks": [],
        "putz_count": count + len(putz_pages),
        "naechster_abstand": abstand,
        "ist_kuerzlich_dran": recent or too_close,
        "ist_zu_dicht_dran": too_close,
        "ist_neu": new,
    }


EMPTY_WEEK = {"member_ids": [], "member_count": 0}


# --------------------------------------------------------------- Zyklus-Mathe

def test_cycles():
    print("\n=== Zyklen & Kalenderwochen ===")
    check("2026 ist ein 53-Wochen-Jahr", cycles.iso_weeks_in_year(2026), 53)
    check("2027 ist ein 52-Wochen-Jahr", cycles.iso_weeks_in_year(2027), 52)

    check("KW 1 -> Zyklus 1", cycles.cycle_of_week(1), 1)
    check("KW 5 -> Zyklus 2", cycles.cycle_of_week(5), 2)
    check("KW 53 -> Zyklus 13 (kein 14.)", cycles.cycle_of_week(53), 13)

    check("Zyklus 1/2026", cycles.weeks_in_cycle(1, 2026), [1, 2, 3, 4])
    check("Zyklus 13/2026 schluckt KW 53", cycles.weeks_in_cycle(13, 2026), [49, 50, 51, 52, 53])
    check("Zyklus 13/2027 endet bei 52", cycles.weeks_in_cycle(13, 2027), [49, 50, 51, 52])

    check("KW 4 ist Zyklusende", cycles.is_last_week_of_cycle(4, 2026), True)
    check("KW 52/2026 ist kein Zyklusende", cycles.is_last_week_of_cycle(52, 2026), False)
    check("KW 53/2026 ist Zyklusende", cycles.is_last_week_of_cycle(53, 2026), True)

    check(
        "nach KW 4/2026 kommt KW 5-8",
        cycles.next_cycle_weeks(4, 2026),
        [(5, 2026), (6, 2026), (7, 2026), (8, 2026)],
    )
    check(
        "nach KW 53/2026 kommt KW 1-4/2027",
        cycles.next_cycle_weeks(53, 2026),
        [(1, 2027), (2, 2027), (3, 2027), (4, 2027)],
    )

    check("Abstand über Jahresgrenze", cycles.weeks_between(52, 2025, 1, 2026), 1)
    check("Abstand innerhalb des Jahres", cycles.weeks_between(1, 2026, 13, 2026), 12)


# ------------------------------------------------------------------- Auslosung

def test_raffle():
    print("\n=== Auslosung ===")

    # Wer vor einer Lockerung im Topf war, muss gesetzt bleiben.
    ideal = member("IDEAL")
    others = [member(f"R{i}", recent=True) for i in range(5)]
    picks = Counter()
    for _ in range(300):
        picks.update(m["id"] for m in raffle.select_crew([ideal] + others, EMPTY_WEEK, 2))
    check("Idealkandidat wird immer gesetzt", picks["IDEAL"], 300)
    check("Restplatz wird verlost", len([k for k in picks if k != "IDEAL"]), 5)

    # Alt/Neu-Mischung
    pool = [member(f"N{i}", new=True) for i in range(6)] + [member(f"A{i}") for i in range(6)]
    mixes = Counter()
    for _ in range(300):
        crew = raffle.select_crew(pool, EMPTY_WEEK, 4)
        mixes[sum(1 for m in crew if m["ist_neu"])] += 1
    check("immer 2 neue + 2 alte", dict(mixes), {2: 300})

    # Schon eingetragene Mitglieder
    with_one = {"member_ids": ["N0"], "member_count": 1}
    doubled = any(
        m["id"] == "N0" for _ in range(50) for m in raffle.select_crew(pool, with_one, 3)
    )
    check("bereits Eingetragene werden nicht erneut gezogen", doubled, False)

    mixes2 = Counter()
    for _ in range(200):
        crew = raffle.select_crew(pool, with_one, 3)
        mixes2[1 + sum(1 for m in crew if m["ist_neu"])] += 1
    check("Mischung zählt Eingetragene mit", dict(mixes2), {2: 200})

    # Eskalation der Einsatz-Obergrenze
    check("greift bis ≤3 Einsätze", len(raffle.select_crew([member(f"H{i}", count=3) for i in range(4)], EMPTY_WEEK, 4)), 4)
    check("stoppt oberhalb von 3 Einsätzen", len(raffle.select_crew([member(f"X{i}", count=4) for i in range(4)], EMPTY_WEEK, 4)), 0)

    # Der harte Mindestabstand darf durch keine Fallback-Stufe aufgeweicht werden.
    solo = [member("SOLO")] + [member(f"B{i}", too_close=True) for i in range(8)]
    check(
        "Mindestabstand ist nicht lockerbar",
        [m["id"] for m in raffle.select_crew(solo, EMPTY_WEEK, 4)],
        ["SOLO"],
    )


def test_enrich():
    print("\n=== enrich_members ===")
    week_pages = {
        "by_page_id": {
            "nah": {"kw": 3, "year": 2027, "page_id": "nah"},
            "fern": {"kw": 20, "year": 2026, "page_id": "fern"},
        }
    }
    nah = member("NAH", putz_pages=["nah"])
    fern = member("FERN", putz_pages=["fern"])
    extra = member("EXTRA")
    extra["extra_weeks"] = [(2, 2027)]

    raffle.enrich_members([nah, fern, extra], week_pages, 1, 2027)

    check("Einsatz 2 Wochen entfernt -> hart geblockt", nah["ist_zu_dicht_dran"], True)
    check("Einsatz 33 Wochen entfernt -> frei", fern["ist_zu_dicht_dran"], False)
    check("... und außerhalb der Schonfrist", fern["ist_kuerzlich_dran"], False)
    check("in diesem Lauf vergebener Einsatz blockt", extra["ist_zu_dicht_dran"], True)
    check("... und zählt als Einsatz", extra["putz_count"], 1)


# ---------------------------------------------------------------- Kompletter Lauf

def test_plan_flow():
    print("\n=== Plan-Lauf (Jahreswechsel 2026 -> 2027) ===")

    writes = []
    original = (
        notion.update_page_members,
        notion.set_week_status,
        notion.create_week_page,
        slack_utils.get_slack_user_id,
        slack_utils.post_channel,
        slack_utils.send_dm,
    )

    notion.update_page_members = lambda pid, ids: writes.append(("update", pid, len(ids))) or True
    notion.set_week_status = lambda pid, s: writes.append(("status", pid, s)) or True
    notion.create_week_page = lambda kw, year, ids, status="Geplant": (
        writes.append(("create", kw, year, len(ids), status)) or (f"page-{kw}", f"https://notion.so/kw{kw}")
    )
    slack_utils.get_slack_user_id = lambda email: f"U{email.split('@')[0].upper()}" if email else None
    slack_utils.post_channel = lambda text, channel=None: True
    slack_utils.send_dm = lambda m, text: "123.456"

    try:
        members = [member(f"N{i}", new=True) for i in range(10)] + [member(f"A{i}") for i in range(10)]
        members.append(member("KUERZLICH", putz_pages=["w50"]))
        lookup = {m["id"]: m for m in members}
        lookup["FREIWILLIG"] = member("FREIWILLIG")

        week_pages = {
            "by_week": {
                (1, 2027): {"page_id": "p1", "page_url": "u1", "kw": 1, "year": 2027,
                            "member_ids": ["FREIWILLIG"], "member_count": 1,
                            "status": "Geplant", "archiv": False},
                (3, 2027): {"page_id": "p3", "page_url": "u3", "kw": 3, "year": 2027,
                            "member_ids": [], "member_count": 0,
                            "status": config.WEEK_STATUS_BLOCKED, "archiv": False},
            },
            "by_page_id": {
                "w50": {"page_id": "w50", "kw": 50, "year": 2026, "member_ids": ["KUERZLICH"],
                        "member_count": 1, "status": "Erledigt", "archiv": False, "page_url": ""},
            },
        }

        summary = scheduler.plan_next_cycle(week_pages, members, lookup, 53, 2026)
        planned = {kw: [m["id"] for m in crew] for kw, crew, _ in summary}

        check("gesperrte Woche wird übersprungen", 3 in planned, False)
        check("drei Wochen geplant", sorted(planned), [1, 2, 4])
        check("jede Woche voll besetzt", {kw: len(ids) for kw, ids in planned.items()}, {1: 4, 2: 4, 4: 4})
        check("Freiwilliger bleibt eingetragen", planned[1][0], "FREIWILLIG")

        assigned = [mid for ids in planned.values() for mid in ids]
        check("niemand doppelt im Zyklus", len(assigned), len(set(assigned)))
        check("Mitglied in Schonfrist bleibt außen vor", "KUERZLICH" in assigned, False)

        for kw, ids in planned.items():
            neu = sum(1 for mid in ids if lookup[mid]["ist_neu"])
            check(f"KW {kw}: 2 neue + 2 alte", neu, 2)

        check("bestehende Seite wird geupdated", ("update", "p1", 4) in writes, True)
        check("fehlende Seiten werden angelegt", sum(1 for w in writes if w[0] == "create"), 2)
        check("volle Crew bekommt Status", all(w[-1] == config.WEEK_STATUS_FULL for w in writes if w[0] in ("create", "status")), True)
    finally:
        (
            notion.update_page_members,
            notion.set_week_status,
            notion.create_week_page,
            slack_utils.get_slack_user_id,
            slack_utils.post_channel,
            slack_utils.send_dm,
        ) = original


def main():
    test_cycles()
    test_raffle()
    test_enrich()
    test_plan_flow()

    print("\n" + "=" * 50)
    if FAILS:
        print(f"❌ {len(FAILS)} Test(s) fehlgeschlagen:")
        for failure in FAILS:
            print(failure)
        return 1
    print("✅ Alle Tests bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
