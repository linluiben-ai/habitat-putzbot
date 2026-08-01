"""Alle Notion-Zugriffe: Queries, Lookups, Schreiboperationen."""

import unicodedata

import requests

import cycles
from config import (
    DRY_RUN,
    DS_A_ID,
    DS_B_ID,
    EMAIL_DOMAIN,
    HEADERS,
    NOTION_API,
    PUTZPLAN_RELATION_PROP,
    PUTZSTATUS_ELIGIBLE,
    TEMPLATE_ID,
    WEEK_STATUS_PLANNED,
    debug,
)


def clean_string(text):
    """Kleinschreibung ohne Umlaute/Diakritika — für generierte E-Mail-Adressen.

    Leerzeichen fallen ersatzlos weg: mehrteilige Nachnamen wie „van de Ven"
    ergaben sonst `remco.van de ven@…`, und ein Leerzeichen ist in einer
    Adresse ungültig — der Lookup scheitert dann garantiert. Ob die Adresse
    ohne Leerzeichen die richtige ist, bleibt geraten; verlässlich wird das
    erst über `Interne Email`.
    """
    text = text.lower()
    for umlaut, replacement in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        text = text.replace(umlaut, replacement)
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    return "".join(text.split())


# --- Low-Level ---

def query_data_source(ds_id, filter_payload=None):
    """Query mit Pagination — Notion liefert max. 100 Seiten pro Request."""
    url = f"{NOTION_API}/data_sources/{ds_id}/query"
    results = []
    cursor = None

    while True:
        payload = {}
        if filter_payload:
            payload["filter"] = filter_payload
        if cursor:
            payload["start_cursor"] = cursor

        response = requests.post(url, json=payload, headers=HEADERS)
        if response.status_code != 200:
            print(f"❌ Notion-Query fehlgeschlagen ({ds_id}): {response.text}")
            return None

        data = response.json()
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    debug(f"Query auf {ds_id}: {len(results)} Seiten geladen.")
    return results


def _prop(props, name, kind, default=None):
    """Wert einer Property lesen, ohne bei fehlender Property zu knallen."""
    return props.get(name, {}).get(kind, default)


def _title_text(props):
    title_prop = next((v for v in props.values() if v.get("type") == "title"), None)
    if not title_prop or not title_prop.get("title"):
        return None
    return title_prop["title"][0]["text"]["content"]


def _relation_ids(props, name):
    relation = _prop(props, name, "relation", []) or []
    if props.get(name, {}).get("has_more"):
        debug(f"⚠️ Relation '{name}' hat mehr als 25 Einträge — Rest wird nicht gelesen.")
    return [item["id"] for item in relation]


# --- Putzplan (DS_B) ---

def get_week_pages():
    """Alle Putzplan-Seiten als {(kw, jahr): seiten-dict}.

    Ein einziger Query statt einer Abfrage pro Woche — wird sowohl für den
    Wochen-Lookup als auch für 'wann hat wer zuletzt geputzt' gebraucht.
    """
    pages = query_data_source(DS_B_ID)
    if pages is None:
        return None

    by_week = {}
    by_page_id = {}

    for page in pages:
        props = page["properties"]
        kw = _prop(props, "Kalenderwoche", "number")
        year = _prop(props, "Jahr", "number")

        if kw is None:
            continue
        if year is None:
            debug(f"⚠️ Seite '{_title_text(props)}' hat kein Jahr — wird ignoriert.")
            continue

        # Sammelseiten wie 'Ausgetragen' (KW 0) oder 'Postponed' (KW 54) sind
        # keine echten Wochen. Sie dürfen weder als Putzeinsatz zählen noch in
        # die Abstandsrechnung einfließen — sonst sähe jede:r, der dort geparkt
        # ist, aus wie frisch geputzt.
        if not 1 <= int(kw) <= cycles.iso_weeks_in_year(int(year)):
            debug(f"'{_title_text(props)}' (KW {int(kw)}) ist keine echte Kalenderwoche — ignoriert.")
            continue

        entry = {
            "page_id": page["id"],
            "page_url": page["url"],
            "kw": int(kw),
            "year": int(year),
            "member_ids": _relation_ids(props, "Mitglieder"),
            "status": (_prop(props, "Status", "status") or {}).get("name"),
            "archiv": _prop(props, "Archiv", "checkbox", False),
        }
        entry["member_count"] = len(entry["member_ids"])

        by_week[(entry["kw"], entry["year"])] = entry
        by_page_id[page["id"]] = entry

    return {"by_week": by_week, "by_page_id": by_page_id}


def notion_lookup(kw, year, week_pages):
    """Status einer einzelnen Woche. `page_status` ist 'exists' oder 'empty'."""
    entry = week_pages["by_week"].get((kw, year))
    if not entry:
        return {
            "page_status": "empty",
            "kw": kw,
            "year": year,
            "page_id": None,
            "page_url": None,
            "member_ids": [],
            "member_count": 0,
            "status": None,
            "archiv": False,
        }
    return dict(entry, page_status="exists")


def update_page_members(page_id, member_ids):
    """Mitglieder-Relation einer Wochenseite komplett überschreiben."""
    if DRY_RUN:
        print(f"   🧪 [DRY RUN] würde Seite {page_id} auf {len(member_ids)} Mitglieder setzen.")
        return True

    response = requests.patch(
        f"{NOTION_API}/pages/{page_id}",
        json={"properties": {"Mitglieder": {"relation": [{"id": mid} for mid in member_ids]}}},
        headers=HEADERS,
    )
    if response.status_code == 200:
        print(f"   ✅ Seite geupdated ({len(member_ids)} Mitglieder).")
        return True

    print(f"   ❌ Fehler beim Update: {response.text}")
    return False


def create_week_page(kw, year, member_ids, status=WEEK_STATUS_PLANNED):
    """Neue Wochenseite aus dem Template. Gibt (page_id, page_url) zurück."""
    title = f"Putzcrew KW {kw}"

    if DRY_RUN:
        print(f"   🧪 [DRY RUN] würde Seite '{title}' ({year}) mit {len(member_ids)} Mitgliedern anlegen.")
        return None, None

    payload = {
        "parent": {"data_source_id": DS_B_ID},
        "template": {"type": "template_id", "template_id": TEMPLATE_ID},
        # Überschreiben die Werte aus dem Template.
        # 'children' darf NICHT mit rein, solange 'template' genutzt wird!
        "properties": {
            "Titel": {"title": [{"text": {"content": title}}]},
            "Mitglieder": {"relation": [{"id": mid} for mid in member_ids]},
            "Kalenderwoche": {"number": kw},
            "Jahr": {"number": year},
            "Status": {"status": {"name": status}},
        },
    }

    response = requests.post(f"{NOTION_API}/pages", json=payload, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ Seite '{title}' ({year}) aus Template erstellt.")
        return data["id"], data["url"]

    print(f"   ❌ Template-Fehler: {response.text}")
    return None, None


def set_week_status(page_id, status):
    """Status einer Wochenseite setzen (z.B. auf 'Crew voll')."""
    if DRY_RUN:
        print(f"   🧪 [DRY RUN] würde Status von {page_id} auf '{status}' setzen.")
        return True

    response = requests.patch(
        f"{NOTION_API}/pages/{page_id}",
        json={"properties": {"Status": {"status": {"name": status}}}},
        headers=HEADERS,
    )
    if response.status_code != 200:
        print(f"   ⚠️ Status konnte nicht gesetzt werden: {response.text}")
        return False
    return True


# --- Mitgliederliste (DS_A) ---

MEMBER_FILTER = {
    "and": [
        {"property": "Austrittsdatum", "date": {"is_empty": True}},
        {"property": "Onboarding: Status", "select": {"equals": "Erledigt"}},
        {"property": "Mitgliedsstatus", "multi_select": {"does_not_contain": "passives Mitglied"}},
        {"property": "Mitgliedsstatus", "multi_select": {"does_not_contain": "Fördermitglied"}},
        {
            "or": [
                {"property": "Mitgliedsstatus", "multi_select": {"contains": "Vereinsmitglied"}},
                {"property": "Mitgliedsstatus", "multi_select": {"contains": "Vorläufiges Mitglied"}},
                {"property": "Mitgliedsstatus", "multi_select": {"contains": "Vorläufiges Mitglied (+1 Jahr)"}},
                {"property": "Mitgliedsstatus", "multi_select": {"contains": "Jugendliches Mitglied"}},
            ]
        },
        # Putzstatus: nur 'Normal' oder leer sind losbar.
        # 'Ausgetragen'/'Neu'/'Priorität'/'Postponed' fallen hier raus.
        {
            "or": [
                {"property": "Putzstatus", "select": {"is_empty": True}},
                *[
                    {"property": "Putzstatus", "select": {"equals": value}}
                    for value in PUTZSTATUS_ELIGIBLE
                    if value is not None
                ],
            ]
        },
    ]
}


def get_eligible_members():
    """Losbare Mitglieder — gefiltert nach Mitgliedsstatus, Onboarding und Putzstatus."""
    members = _load_members(MEMBER_FILTER)
    if members is not None:
        debug(f"{len(members)} losbare Mitglieder nach Notion-Filter.")
    return members


def get_all_members():
    """Alle Mitglieder, ungefiltert.

    Gebraucht, um Namen/E-Mails von Leuten aufzulösen, die sich freiwillig
    eingetragen haben, aber selbst nicht losbar sind (z.B. Putzstatus
    'Ausgetragen') — sonst könnte der Bot sie nicht in Slack erwähnen.
    """
    return _load_members(None)


def _load_members(filter_payload):
    pages = query_data_source(DS_A_ID, filter_payload)
    if pages is None:
        return None

    members = []
    for page in pages:
        props = page["properties"]

        full_name = _title_text(props)
        if not full_name:
            continue

        # 'Interne Email' bevorzugen, sonst aus "Nachname, Vorname" ableiten.
        # Die Herkunft wird mitgeführt: eine abgeleitete Adresse ist eine
        # Vermutung und die häufigste Ursache dafür, dass jemand keine DM
        # bekommt. Der Modus `tags` wertet das aus.
        email = _prop(props, "Interne Email", "email")
        email_quelle = "Interne Email" if email else None
        if not email and "," in full_name:
            nachname, vorname = (part.strip() for part in full_name.split(",", 1))
            email = f"{clean_string(vorname)}.{clean_string(nachname)}@{EMAIL_DOMAIN}"
            email_quelle = "abgeleitet"

        eintritt = _prop(props, "Eintrittsdatum", "date") or {}

        members.append(
            {
                "id": page["id"],
                "name": full_name,
                "email": email,
                "email_quelle": email_quelle,
                "eintrittsdatum": eintritt.get("start"),
                "putzstatus": (_prop(props, "Putzstatus", "select") or {}).get("name"),
                "putz_page_ids": _relation_ids(props, PUTZPLAN_RELATION_PROP),
                "extra_weeks": [],  # in diesem Lauf vergebene Einsätze, s. raffle.enrich_members
            }
        )

    return members
