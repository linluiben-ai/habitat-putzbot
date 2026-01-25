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
EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAIN")

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


def main():
    print("🤖 Starte Putzplan-Lotterie (Direct API Call)...")

    # 1. Notion: Mitglieder abfragen
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
        print(f"❌ Notion API Fehler: {response.text}")
        return

    data = response.json()
    candidates = []

    for member in data.get("results", []):
        icon = member["icon"]
        if icon and icon["type"] == "emoji":
            emoji = icon["emoji"]
        else:
            emoji = None
        not_in_question = not (emoji == "❓")

        props = member["properties"]

        # Check: Hat die Person schon mal geputzt? (Relation in DB A)
        # Wir prüfen, ob die Liste der Relationen leer ist
        putz_relation = props.get("Putzplan", {}).get("relation", [])

        if not_in_question:
            if not putz_relation:
                try:
                    # Titel-Property finden
                    title_prop = next((v for k, v in props.items() if v["type"] == "title"), None)
                    if not title_prop or not title_prop["title"]:
                        continue

                    full_name_raw = title_prop["title"][0]["text"]["content"]

                    if ',' in full_name_raw:
                        parts = full_name_raw.split(',')
                        nachname = clean_string(parts[0].strip())
                        vorname = clean_string(parts[1].strip())
                        email = f"{vorname}.{nachname}@{EMAIL_DOMAIN}"

                        candidates.append({
                            "id": member["id"],
                            "name": full_name_raw,
                            "email": email
                        })
                except Exception as e:
                    print(f"⚠️ Fehler beim Parsen von {member['id']}: {e}")

    print(f"✅ {len(candidates)} Mitglieder im Lostopf.")

    if not candidates:
        print("❌ Keine Kandidaten gefunden.")
        return
    else:
        for c in candidates:
            print(c["name"])
            print(c["email"])
            print("------------------")

    # 2. Zufällige Auswahl
    selected = random.sample(candidates, min(len(candidates), 4))

    # 3. Neue Seite in DB B erstellen
    kw = datetime.now().isocalendar()[1] + 1
    create_url = "https://api.notion.com/v1/pages"

    new_page_data = {
        "parent": {"data_source_id": DS_B_ID},
        "properties": {
            "Woche": {"title": [{"text": {"content": f"Putzcrew KW {kw}"}}]},
            "Test": {"relation": [{"id": p["id"]} for p in selected]}
        }
    }

    res_create = requests.post(create_url, json=new_page_data, headers=HEADERS)
    if res_create.status_code == 200:
        print(f"📝 Notion Seite für KW {kw} erstellt.")
    else:
        print(f"❌ Fehler beim Erstellen der Seite: {res_create.text}")
        return

    # 4. Slack Nachricht
    slack_tags = []
    for person in selected:
        s_id = get_slack_user_id(person["email"])
        if s_id:
            slack_tags.append(f"<@{s_id}>")
        else:
            # Fallback auf Vorname
            name_part = person["name"].split(',')[-1].strip()
            slack_tags.append(name_part)

    msg = f"🧹 *Putzplan KW {kw} ist da!* 🧹\n\nDiese Woche sind dran: {', '.join(slack_tags)}"

    try:
        slack.chat_postMessage(channel=SLACK_CHANNEL_ID, text=msg)
        print("📨 Slack Nachricht gesendet.")
    except SlackApiError as e:
        print(f"❌ Slack Fehler: {e}")


if __name__ == "__main__":
    main()