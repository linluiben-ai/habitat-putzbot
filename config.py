"""Zentrale Konfiguration: Env-Variablen, Clients, Konstanten."""

import os
import sys

from slack_sdk import WebClient

# --- Env ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
SLACK_TOKEN = os.environ.get("SLACK_TOKEN")
DS_A_ID = os.environ.get("DS_A_ID")  # Mitgliederliste
DS_B_ID = os.environ.get("DS_B_ID")  # Putzplan
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
TEMPLATE_ID = os.environ.get("TEMPLATE_ID")

# Zum Testen: wenn gesetzt, gehen ALLE DMs an diese Slack-User-ID statt an die
# echten Mitglieder. Im Sandbox-Workspace stimmen die E-Mail-Adressen sonst
# nicht mit denen aus Notion überein und der Lookup läuft ins Leere.
SLACK_TEST_USER_ID = os.environ.get("SLACK_TEST_USER_ID")

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
# Plan-Lauf erzwingen, auch wenn gerade nicht die letzte Woche eines Zyklus ist (zum Testen).
FORCE_PLAN = os.environ.get("FORCE_PLAN", "false").lower() == "true"

# --- Notion API ---
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION,
}

EMAIL_DOMAIN = "das-habitat.de"

# --- Putzplan-Regeln ---
CREW_SIZE = 4                 # Zielgröße einer Wochen-Crew
CYCLE_LENGTH_WEEKS = 4        # Wochen pro Zyklus
CYCLES_PER_YEAR = 13          # 13 * 4 = 52 (KW 53 gehört zu Zyklus 13)

MAX_CLEANINGS_CAP = 3         # niemand soll öfter als 3x ran
RECENCY_WEEKS = 12            # 3 Zyklen "Schonfrist" nach dem letzten Einsatz (weich, wird in Fallbacks gelockert)
MIN_WEEKS_BETWEEN = 4         # Mindestabstand zwischen zwei Einsätzen (hart, wird nie gelockert)
NEW_MEMBER_DAYS = 365         # jünger als das = "neues Mitglied"
TARGET_NEW = 2                # Wunsch-Mischung pro Woche
TARGET_OLD = 2

# Nur diese Putzstatus-Werte dürfen gelost werden (None = Property leer).
PUTZSTATUS_ELIGIBLE = (None, "Normal")

# Wochen mit diesem Status fasst der Bot nicht an.
WEEK_STATUS_BLOCKED = "Nicht auswählen"
WEEK_STATUS_PLANNED = "Geplant"
WEEK_STATUS_FULL = "Crew voll"
WEEK_STATUS_DONE = "Erledigt"

# --- Reschedule (Phase 6, hier nur vorkonfiguriert) ---
RESCHEDULE_ENABLED = False    # solange False: keine ❌-Option in den DMs
RESCHEDULE_MAX_CYCLES_AHEAD = 10
RESCHEDULE_ASK_AT = 5         # ab so vielen Leuten: Crew fragen, ob jemand tauscht
RESCHEDULE_DENY_AT = 6        # ab so vielen Leuten: Zielwoche ablehnen

slack = WebClient(token=SLACK_TOKEN)

REQUIRED_ENV = {
    "NOTION_TOKEN": NOTION_TOKEN,
    "SLACK_TOKEN": SLACK_TOKEN,
    "DS_A_ID": DS_A_ID,
    "DS_B_ID": DS_B_ID,
    "SLACK_CHANNEL_ID": SLACK_CHANNEL_ID,
    "TEMPLATE_ID": TEMPLATE_ID,
}


def debug(message):
    """Ausgabe nur bei DEBUG=true."""
    if DEBUG:
        print(f"   🐛 {message}")


def check_env():
    """Bricht früh ab, wenn Env-Variablen fehlen — statt später mit kryptischem API-Fehler."""
    missing = [name for name, value in REQUIRED_ENV.items() if not value]
    if missing:
        print(f"❌ Fehlende Env-Variablen: {', '.join(missing)}")
        sys.exit(1)
