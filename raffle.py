"""Kandidatenpool bauen und Putzcrew auslosen.

Der Pool wird in Stufen gebaut, von streng nach locker:

    Einsätze ≤1 & länger nicht dran  ->  Einsätze ≤1
    Einsätze ≤2 & länger nicht dran  ->  Einsätze ≤2
    Einsätze ≤3 & länger nicht dran  ->  Einsätze ≤3

Reichen die Kandidaten einer Stufe nicht aus, werden **alle** von ihnen fix
gesetzt und nur die Restplätze auf der nächsten (lockereren) Stufe besetzt.
So verliert niemand seinen Platz, nur weil die Kriterien danach aufgeweicht
werden mussten.

Die Alt/Neu-Mischung (2+2) ist das weichste Kriterium und greift erst beim
eigentlichen Ziehen innerhalb der finalen Stufe.
"""

import random
from datetime import date

import cycles
from config import (
    MAX_CLEANINGS_CAP,
    MIN_WEEKS_BETWEEN,
    NEW_MEMBER_DAYS,
    RECENCY_WEEKS,
    TARGET_NEW,
    TARGET_OLD,
    debug,
)


def _is_new_member(eintrittsdatum, today):
    """Neu = weniger als ein Jahr dabei. Ohne Eintrittsdatum gilt jemand als 'alter Hase'."""
    if not eintrittsdatum:
        return False
    try:
        eintritt = date.fromisoformat(eintrittsdatum[:10])
    except ValueError:
        return False
    return (today - eintritt).days < NEW_MEMBER_DAYS


def enrich_members(members, week_pages, kw, year):
    """Pro Mitglied Einsatzzahl, Abstand zum nächsten Einsatz und Alt/Neu berechnen.

    Muss pro Zielwoche neu laufen, weil der Abstand von der Zielwoche abhängt.
    `extra_weeks` enthält Einsätze, die dieser Lauf selbst schon vergeben hat und
    die daher noch nicht in der Notion-Relation stehen.
    """
    target_index = cycles.week_index(kw, year)
    today = date.today()

    for member in members:
        assigned = []
        for page_id in member["putz_page_ids"]:
            entry = week_pages["by_page_id"].get(page_id)
            if entry:
                assigned.append((entry["kw"], entry["year"]))
        assigned.extend(member.get("extra_weeks", []))

        distances = [
            abs(cycles.week_index(w_kw, w_year) - target_index) for w_kw, w_year in assigned
        ]

        member["putz_count"] = len(member["putz_page_ids"]) + len(member.get("extra_weeks", []))
        member["naechster_abstand"] = min(distances) if distances else None

        # Weich: Schonfrist von 3 Zyklen. Wird in den Fallback-Stufen aufgeweicht.
        member["ist_kuerzlich_dran"] = (
            member["naechster_abstand"] is not None
            and member["naechster_abstand"] < RECENCY_WEEKS
        )
        # Hart: zwei Einsätze im selben Zyklus (bzw. dichter als MIN_WEEKS_BETWEEN)
        # sind auch dann tabu, wenn die Schonfrist gelockert wird — sonst könnte
        # jemand in einem Planungslauf für zwei Wochen gleichzeitig gezogen werden.
        member["ist_zu_dicht_dran"] = (
            member["naechster_abstand"] is not None
            and member["naechster_abstand"] < MIN_WEEKS_BETWEEN
        )
        member["ist_neu"] = _is_new_member(member["eintrittsdatum"], today)

    return members


def _tiers():
    """Stufen von streng nach locker: (max. Einsätze, Schonfrist beachten)."""
    for max_cleanings in range(1, MAX_CLEANINGS_CAP + 1):
        yield max_cleanings, True
        yield max_cleanings, False


def _mix(members):
    """(neue, alte) in einer Mitgliederliste."""
    new = sum(1 for m in members if m["ist_neu"])
    return new, len(members) - new


def _balanced_sample(pool, count, current_new, current_old):
    """`count` Leute ziehen und dabei Richtung 2 neue / 2 alte pro Woche steuern."""
    wanted_new = max(0, TARGET_NEW - current_new)
    wanted_old = max(0, TARGET_OLD - current_old)

    new_pool = [m for m in pool if m["ist_neu"]]
    old_pool = [m for m in pool if not m["ist_neu"]]

    take_new = min(wanted_new, len(new_pool), count)
    take_old = min(wanted_old, len(old_pool), count - take_new)

    picked = random.sample(new_pool, take_new) + random.sample(old_pool, take_old)

    # Rest ohne Rücksicht auf die Mischung auffüllen
    shortfall = count - len(picked)
    if shortfall > 0:
        picked_ids = {m["id"] for m in picked}
        leftovers = [m for m in pool if m["id"] not in picked_ids]
        picked += random.sample(leftovers, min(shortfall, len(leftovers)))

    debug(f"Gezogen: {take_new} neue, {take_old} alte, {len(picked) - take_new - take_old} beliebig.")
    return picked


def select_crew(members, week, needed, exclude_ids=()):
    """Kandidaten stufenweise sammeln und `needed` Mitglieder ziehen."""
    if needed <= 0:
        return []

    blocked = set(week["member_ids"]) | set(exclude_ids)
    base = [m for m in members if m["id"] not in blocked]

    already_on_page = [m for m in members if m["id"] in set(week["member_ids"])]
    current_new, current_old = _mix(already_on_page)

    selected = []
    chosen_ids = set()

    for max_cleanings, respect_recency in _tiers():
        remaining = needed - len(selected)
        if remaining <= 0:
            break

        pool = [
            m
            for m in base
            if m["id"] not in chosen_ids
            and not m["ist_zu_dicht_dran"]
            and m["putz_count"] <= max_cleanings
            and not (respect_recency and m["ist_kuerzlich_dran"])
        ]
        if not pool:
            continue

        label = f"≤{max_cleanings} Einsätze" + (" & Schonfrist" if respect_recency else "")

        if len(pool) <= remaining:
            # Zu wenige für die Restplätze -> alle fix setzen, Rest kommt aus der nächsten Stufe
            debug(f"Stufe '{label}': {len(pool)} Kandidaten, alle gesetzt (brauchte {remaining}).")
            selected.extend(pool)
            chosen_ids.update(m["id"] for m in pool)
            continue

        debug(f"Stufe '{label}': {len(pool)} Kandidaten, ziehe {remaining}.")
        picked_new, picked_old = _mix(selected)
        selected.extend(
            _balanced_sample(pool, remaining, current_new + picked_new, current_old + picked_old)
        )
        break

    if len(selected) < needed:
        print(
            f"   ⚠️ Nur {len(selected)} von {needed} Plätzen besetzt — "
            f"der Kandidatenpool ist auch nach allen Fallbacks zu klein."
        )

    return selected


def describe_candidates(members, week):
    """Übersicht für DRY_RUN/DEBUG: wer wäre auf welcher Stufe im Topf?"""
    blocked = set(week["member_ids"])
    lines = []
    for max_cleanings, respect_recency in _tiers():
        pool = [
            m
            for m in members
            if m["id"] not in blocked
            and not m["ist_zu_dicht_dran"]
            and m["putz_count"] <= max_cleanings
            and not (respect_recency and m["ist_kuerzlich_dran"])
        ]
        label = f"≤{max_cleanings} Einsätze" + (" & Schonfrist" if respect_recency else "")
        new, old = _mix(pool)
        lines.append(f"      Stufe '{label}': {len(pool)} Kandidaten ({new} neu / {old} alt)")
    return lines
