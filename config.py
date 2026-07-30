"""Zentrale Konfiguration: Env-Variablen, Clients, Konstanten."""

import os
import sys
from pathlib import Path

from slack_sdk import WebClient


def _load_dotenv():
    """Minimaler .env-Loader (KEY=VALUE pro Zeile, '#' ist Kommentar).

    Bewusst ohne Abhängigkeit und bewusst mit `setdefault`: echte
    Umgebungsvariablen gewinnen immer, damit die GitHub-Action-Secrets nicht
    plötzlich von einer lokalen Datei überschrieben werden. Die Datei liegt
    neben config.py, nicht im aktuellen Arbeitsverzeichnis.
    """
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Ausgabe enthält durchgehend Emoji und Umlaute. Windows-Konsolen laufen je
# nach Shell auf cp1252 und werfen dann UnicodeEncodeError mitten im Lauf.
# Beide Einstiegspunkte importieren config zuerst, deshalb steht das hier.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # z.B. umgeleitete Streams ohne reconfigure

# --- Env ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
SLACK_TOKEN = os.environ.get("SLACK_TOKEN")
DS_A_ID = os.environ.get("DS_A_ID")  # Mitgliederliste
DS_B_ID = os.environ.get("DS_B_ID")  # Putzplan
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
TEMPLATE_ID = os.environ.get("TEMPLATE_ID")

# Auf die Notion-Testkopien umschalten. Bewusst ein eigener Schalter statt
# "einfach DS_A_ID überschreiben": so kann man nicht aus Versehen mit den
# Produktivdaten testen, weil man vergessen hat, eine Variable zurückzusetzen.
USE_TEST_DATA = os.environ.get("USE_TEST_DATA", "false").lower() == "true"
TEST_DS_A_ID = os.environ.get("TEST_DS_A_ID")
TEST_DS_B_ID = os.environ.get("TEST_DS_B_ID")
TEST_TEMPLATE_ID = os.environ.get("TEST_TEMPLATE_ID")

# Name der Relation von der Mitgliederliste zum Putzplan.
# Eine duplizierte Putzplan-DB legt auf der Mitgliederliste eine ZWEITE
# Relations-Property an; die echte bleibt unberührt. Beim Testen muss der Bot
# die Kopie lesen, sonst sieht er die Einsätze aus den Testläufen nicht und
# lost jedes Mal aus einem "noch nie geputzt"-Zustand.
PUTZPLAN_RELATION_PROP = os.environ.get("PUTZPLAN_RELATION_PROP", "Putzplan")
TEST_PUTZPLAN_RELATION_PROP = os.environ.get("TEST_PUTZPLAN_RELATION_PROP", "Putztest")

if USE_TEST_DATA:
    # DS_B (Putzplan) und Template MÜSSEN Kopien sein — das ist die einzige
    # Datenbank, in die der Bot schreibt. Kein stiller Fallback auf die echten
    # IDs, das wäre genau der Unfall, den dieser Schalter verhindern soll.
    _missing_test = [
        name
        for name, value in (("TEST_DS_B_ID", TEST_DS_B_ID), ("TEST_TEMPLATE_ID", TEST_TEMPLATE_ID))
        if not value
    ]
    if _missing_test:
        sys.exit(f"❌ USE_TEST_DATA=true, aber es fehlen: {', '.join(_missing_test)}")

    DS_B_ID, TEMPLATE_ID = TEST_DS_B_ID, TEST_TEMPLATE_ID
    # DS_A (Mitgliederliste) ist optional: der Bot liest daraus nur, er schreibt
    # nie hinein. Ohne Kopie wird also einfach die echte Liste gelesen.
    DS_A_ID = TEST_DS_A_ID or DS_A_ID
    # Gehört zwingend zur Testkopie dazu — sonst liest der Bot die echte
    # Putzhistorie, deren Seiten-IDs es in der Kopie gar nicht gibt.
    PUTZPLAN_RELATION_PROP = TEST_PUTZPLAN_RELATION_PROP

DATENQUELLE = "🧪 TESTKOPIE" if USE_TEST_DATA else "🔴 PRODUKTIV"

# Zum Testen: wenn gesetzt, gehen ALLE DMs an diese Slack-User-ID statt an die
# echten Mitglieder. Im Sandbox-Workspace stimmen die E-Mail-Adressen sonst
# nicht mit denen aus Notion überein und der Lookup läuft ins Leere.
SLACK_TEST_USER_ID = os.environ.get("SLACK_TEST_USER_ID")

# Auf den Sandbox-Workspace umschalten. Analog zu USE_TEST_DATA ein eigener
# Schalter, damit man zum Testen nicht die produktiven Werte überschreiben und
# hinterher wieder zurückschreiben muss.
SANDBOX = os.environ.get("SANDBOX", "false").lower() == "true"
SANDBOX_SLACK_TOKEN = os.environ.get("SANDBOX_SLACK_TOKEN")
SANDBOX_SLACK_CHANNEL_ID = os.environ.get("SANDBOX_SLACK_CHANNEL_ID")
SANDBOX_SLACK_TEST_USER_ID = os.environ.get("SANDBOX_SLACK_TEST_USER_ID")

if SANDBOX:
    # Token und Kanal sind Pflicht: ein Fallback auf die Produktivwerte hieße,
    # dass ein vermeintlicher Sandbox-Lauf im echten Workspace landet.
    _missing_sandbox = [
        name
        for name, value in (
            ("SANDBOX_SLACK_TOKEN", SANDBOX_SLACK_TOKEN),
            ("SANDBOX_SLACK_CHANNEL_ID", SANDBOX_SLACK_CHANNEL_ID),
        )
        if not value
    ]
    if _missing_sandbox:
        sys.exit(f"❌ SANDBOX=true, aber es fehlen: {', '.join(_missing_sandbox)}")

    SLACK_TOKEN = SANDBOX_SLACK_TOKEN
    SLACK_CHANNEL_ID = SANDBOX_SLACK_CHANNEL_ID
    # Im Sandbox-Workspace hat man eine andere User-ID als im echten.
    SLACK_TEST_USER_ID = SANDBOX_SLACK_TEST_USER_ID or SLACK_TEST_USER_ID

SLACK_ZIEL = "🧪 SANDBOX" if SANDBOX else "🔴 PRODUKTIV"

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

# --- Reschedule ---
RESCHEDULE_ENABLED = True     # False: keine ❌-Option in den DMs
RESCHEDULE_MAX_CYCLES_AHEAD = 10
# Harte Obergrenze: eine Zielwoche wird abgelehnt, sobald dort schon CREW_SIZE
# Leute stehen. Bewusst kein weicher Puffer mit Rückfrage an die Crew — das
# wäre viel Mechanik für einen Fall, der kaum eintritt (geplant wird immer nur
# ein Zyklus im Voraus, weiter entfernte Wochen sind praktisch immer leer).

# Emoji-Namen, wie Slack sie liefert (ohne Doppelpunkte). Mehrere Varianten,
# weil Leute nicht zuverlässig dasselbe Häkchen bzw. Kreuz erwischen.
CONFIRM_REACTIONS = frozenset(
    {"white_check_mark", "heavy_check_mark", "ballot_box_with_check", "+1", "thumbsup"}
)
DECLINE_REACTIONS = frozenset(
    {"x", "negative_squared_cross_mark", "heavy_multiplication_x", "-1", "thumbsdown"}
)

# Slack-Message-Metadata: hängt strukturiert an der Nachricht und kommt beim
# Lesen der Historie wieder mit zurück. Dadurch braucht die Zuordnung
# "welche DM gehört zu welcher Woche" keinen eigenen Speicher.
META_AUSLOSUNG = "putzbot_auslosung"
META_FRAGE = "putzbot_reschedule_frage"

DM_HISTORY_LIMIT = 30         # so viele Nachrichten pro DM-Verlauf ansehen

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
