import os
import random
import unicodedata
import requests
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# --- KONFIGURATION ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
SLACK_TOKEN = os.environ.get("SLACK_TOKEN")
DS_A_ID = os.environ.get("DS_A_ID") # Mitglieder
DS_B_ID = os.environ.get("DS_B_ID") # Putzliste
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
TEMPLATE_ID = os.environ.get("TEMPLATE_ID")
EMAIL_DOMAIN = "das-habitat.de"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

# Notion API Header
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2025-09-03"
}

slack = WebClient(token=SLACK_TOKEN)



def clean_string(text):
    text = text.lower()
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return text.strip()


def get_slack_user_id(email):
    try:
        result = slack.users_lookupByEmail(email=email)
        return result["user"]["id"]
    except SlackApiError:
        return None


def get_current_week_status(ds_id, headers):
    current_kw = datetime.now().isocalendar()[1]

    print(f"🔎 Prüfe Status für KW {current_kw}...")

    # WICHTIG: Standard API nutzt 'databases', nicht 'data_sources' im Pfad für Queries
    query_url = f"https://api.notion.com/v1/data_sources/{ds_id}/query"
    payload = {
        "filter": {
            "property": "Kalenderwoche",
            "number": {
                "equals": current_kw
            }
        }
    }

    response = requests.post(query_url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"⚠️ Fehler beim Checken der Woche: {response.text}")
        return {"page_status": "error", "kw": current_kw}

    data = response.json()
    results = data.get("results", [])

    if not results:
        return {"page_status": "empty", "kw": current_kw, "page_id": None, "existing_count": 0, "existing_ids": []}

    page = results[0]
    page_id = page["id"]
    page_url = page["url"]
    props = page["properties"]

    # Rollup oder Relation zählen
    try:
        # Versuch via Rollup
        rollup_prop = props.get("Anzahl Mitglieder", {}).get("rollup", {})
        existing_count = rollup_prop.get("number", 0)
    except Exception:
        existing_count = 0

    # Fallback: Manuell zählen, wenn Rollup 0 oder Fehler, aber Relation da ist
    existing_rels = props.get("Mitglieder", {}).get("relation", [])
    if existing_count == 0 and existing_rels:
        existing_count = len(existing_rels)

    existing_ids = [rel["id"] for rel in existing_rels]

    return {
        "page_status": "exists",
        "kw": current_kw,
        "page_id": page_id,
        "page_url": page_url,
        "existing_count": existing_count,
        "existing_ids": existing_ids
    }


# Seite updaten
def update_existing_page(page_id, all_ids_combined, headers):
    update_url = f"https://api.notion.com/v1/pages/{page_id}"

    payload = {
        "properties": {
            "Mitglieder": {
                "relation": [{"id": mid} for mid in all_ids_combined]
            }
        }
    }

    res = requests.patch(update_url, json=payload, headers=headers)
    if res.status_code == 200:
        print(f"✅ Seite {page_id} erfolgreich geupdated (Jetzt {len(all_ids_combined)} Mitglieder).")
    else:
        print(f"❌ Fehler beim Update: {res.text}")

def create_page_from_template(ds_id, template_id, title, member_ids, kw, headers):
    url = "https://api.notion.com/v1/pages"

    payload = {
        "parent": {"data_source_id": ds_id},
        "template": {
            "type": "template_id",
            "template_id": template_id
        },
        # Diese Properties überschreiben die Werte im Template:
        "properties": {
            "Titel": {"title": [{"text": {"content": title}}]},
            "Mitglieder": {"relation": [{"id": uid} for uid in member_ids]},
            "Kalenderwoche": {"number": kw}
        }
    }

    # Hinweis: 'children' darf NICHT im payload sein, wenn 'template' genutzt wird!

    res = requests.post(url, json=payload, headers=headers)

    if res.status_code == 200:
        print(f"✅ Seite '{title}' erfolgreich aus Template erstellt.")
        data = res.json()
        return data["id"], data["url"]
    else:
        print(f"❌ Template-Fehler: {res.text}")
        return None, None

def main():
    print("🤖 Starte Putzplan-Lotterie V2")

    # 1. Überprüfen, ob es schon eine Seite für diese Woche gibt
    kw_status = get_current_week_status(DS_B_ID, HEADERS)
    if kw_status.get("page_status") == "error":
        return

    current_kw = kw_status["kw"]
    existing_count = kw_status["existing_count"]
    existing_ids = kw_status["existing_ids"]

    #Ziel: 4 Leute
    needed = 4 - existing_count
    print(f"📅 KW {current_kw}: Bereits {existing_count} Mitglieder. Benötige noch {needed}.")

    # 2. Kandidaten laden (nur nötig, wenn wir losen müssen ODER um Namen für Slack aufzulösen)
    # Wir laden sie immer, damit wir die Namen für die Slack Nachricht haben.

    url = f"https://api.notion.com/v1/data_sources/{DS_A_ID}/query"
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Austrittsdatum",
                    "date": {
                        "is_empty": True
                    }
                },
                {
                    "property": "Onboarding: Status",
                    "select": {
                        "equals": "Erledigt"
                    }
                },
                {
                    "property": "Mitgliedsstatus",
                    "multi_select": {
                        "does_not_contain": "passives Mitglied"
                    }
                },
                {
                    "property": "Mitgliedsstatus",
                    "multi_select": {
                        "does_not_contain": "Fördermitglied"
                    }
                },
                {
                    "or": [
                        {
                            "property": "Mitgliedsstatus",
                            "multi_select": {
                                "contains": "Vereinsmitglied"
                            }
                        },
                        {
                            "property": "Mitgliedsstatus",
                            "multi_select": {
                                "contains": "Vorläufiges Mitglied"
                            }
                        },
                        {
                            "property": "Mitgliedsstatus",
                            "multi_select": {
                                "contains": "Vorläufiges Mitglied (+1 Jahr)"
                            }
                        },
                        {
                            "property": "Mitgliedsstatus",
                            "multi_select": {
                                "contains": "Jugendliches Mitglied"
                            }
                        }
                    ]
                }
            ]
        }
    }

    response = requests.post(url, json=payload, headers=HEADERS)
    if response.status_code != 200:
        print(f"❌ Notion API Fehler (Mitglieder): {response.text}")
        return

    data = response.json()
    all_members_data = data.get("results", [])
    candidates_pool = []
    member_lookup = {}

    for member in all_members_data:
        m_id = member["id"]
        props = member["properties"]

        # Name parsen
        title_prop = next((v for k, v in props.items() if v["type"] == "title"), None)
        if not title_prop or not title_prop["title"]:
            continue
        full_name = title_prop["title"][0]["text"]["content"]

        # E-Mail Logik (Interne Email bevorzugen)
        email = None
        email_prop = props.get("Interne Email", {})
        if email_prop.get("email"):
            email = email_prop["email"]
        else:
            # Fallback generieren
            if ',' in full_name:
                parts = full_name.split(',')
                n = clean_string(parts[0].strip())
                v = clean_string(parts[1].strip())
                email = f"{v}.{n}@{EMAIL_DOMAIN}"

        # In Lookup speichern (für Slack später)
        member_obj = {"id": m_id, "name": full_name, "email": email}
        member_lookup[m_id] = member_obj

        # Prüfen ob Kandidat für Losung:
        # 1. Kein "❓" Emoji
        icon = member.get("icon", {})
        is_questionable = (icon and icon.get("type") == "emoji" and icon.get("emoji") == "❓")

        # 2. Hat noch nicht geputzt (Relation leer)
        putz_rel = props.get("Putzplan", {}).get("relation", [])
        has_cleaned = len(putz_rel) > 0 #HIER STELLSCHRAUBE FÜR MEHRERE ZYKLEN!

        # 3. Ist NICHT schon diese Woche eingetragen (ganz wichtig beim Nachlosen!) - ist das nicht redundant, da bei diesen ja schon has_cleaned True ist
        is_already_in_week = m_id in existing_ids

        if not is_questionable and not has_cleaned and not is_already_in_week:
            candidates_pool.append(member_obj)

    print(f"📊 {len(candidates_pool)} qualifizierte Kandidaten im Lostopf.")

    if not candidates_pool:
        print("❌ Keine Kandidaten gefunden.")
        return
    if DRY_RUN:
        print("\n🧪 DRY RUN: Nur Kandidatenliste, keine Änderungen in Notion oder Slack.\n")
        for i, person in enumerate(sorted(candidates_pool, key=lambda x: x["name"]), start=1):
            print(f"{i:02d}. {person['name']} | {person['email'] or 'keine E-Mail'}")
        return


    # 3. Entscheidung & Aktion
    selected_new = []
    current_page_url = kw_status.get("page_url")

    if needed > 0:
        # CASE A: Wir müssen auffüllen
        draw_count = min(len(candidates_pool), needed)
        if len(candidates_pool) >= needed:
            selected_new = random.sample(candidates_pool, draw_count)
            print(f"🎲 {len(selected_new)} neue Mitglieder ausgelost.")
        elif draw_count > 0:
            selected_new = random.sample(candidates_pool, draw_count)
            print(f"🎲 {len(selected_new)} neue Mitglieder ausgelost. Es waren jedoch {needed} benötigt, also nicht genügend Kandidaten im Lostopf.")
        else:
            print("⚠️ Warnung: Keine Kandidaten im Pool!")

        # IDs zusammenführen (Bestehende + Neue)
        all_ids_final = existing_ids + [p["id"] for p in selected_new]

        if kw_status["page_status"] == "exists":
            # Seite bearbeiten
            update_existing_page(kw_status["page_id"], all_ids_final, HEADERS)
        else:
            # Neue Seite aus Template
            new_id, new_url = create_page_from_template(
                DS_B_ID,
                TEMPLATE_ID,
                f"Putzcrew KW {current_kw}",
                all_ids_final,
                current_kw,
                HEADERS
            )
            if new_url:
                current_page_url = new_url
    else:
        # CASE B: Schon genug Mitglieder
        print("✅ Crew ist bereits vollzählig. Kein Losen nötig.")

    # 4. Slack Nachricht generieren

    # Helper um Slack Tag zu holen
    def get_tag(uid):
        # Daten aus Lookup holen
        mem = member_lookup.get(uid)
        if not mem: return "Unbekannt"

        sid = get_slack_user_id(mem["email"])
        if sid:
            return f"<@{sid}>"
        else:
            # Fallback Name
            return mem["name"].split(',')[-1].strip()

    # Listen für Nachricht
    tags_existing = [get_tag(uid) for uid in existing_ids]
    tags_new = [get_tag(p["id"]) for p in selected_new]

    msg = f"🧹 *Der Putzplan für diese Woche ist da:* 🧹\n\n"

    if needed <= 0 and not selected_new:
        # Alles war schon voll (Freiwillige)
        msg += (f"Diese Woche sind wir schon komplett! Ein riesiges Dankeschön an die Freiwilligen:\n"
               f"{', '.join(tags_existing)} 💚")
    else:
        # Wir haben gelost (gemischt oder komplett neu)
        if tags_existing:
            msg += f"Danke fürs freiwillige Eintragen: {', '.join(tags_existing)} 🙏\n"
        if needed == 4:
            if tags_new:
                msg += f"Dazu wurden vom Bot ausgelost: {', '.join(tags_new)} 🎲\n"
        else:
            if tags_new:
                msg += f"Zusätzlich wurden vom Bot ausgelost: {', '.join(tags_new)} 🎲\n"
    # Link
    if current_page_url:
        # Slack Syntax: <URL|Text>
        msg += f"\n👉 <{current_page_url}|Hier geht's zur Seite in Notion>"
    else:
        print("⚠️ Warnung: Konnte keinen Link zur Notion-Seite generieren.")

    # Nachricht senden
    try:
        slack.chat_postMessage(channel=SLACK_CHANNEL_ID, text=msg)
        print("📨 Slack Nachricht gesendet.")
    except SlackApiError as e:
        print(f"❌ Slack Fehler: {e}")


if __name__ == "__main__":
    main()