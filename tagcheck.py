"""Prüfen, ob sich jedes losbare Mitglied überhaupt in Slack erreichen lässt.

Der Bot findet Leute ausschließlich über ihre E-Mail-Adresse
(`users_lookupByEmail`). Steht in Notion keine `Interne Email`, rät er sie aus
`Nachname, Vorname` — und ein falsch geratener Name fällt erst dann auf, wenn
jemand seine Auslos-DM nicht bekommen hat. Im Sandbox-Workspace lässt sich das
nicht testen, weil dort niemand die echten Adressen hat.

Deshalb dieser Modus: einmal gegen den echten Workspace laufen lassen, das
Ergebnis kommt als DM. Er schreibt nichts nach Notion und postet nichts in
einen Kanal — er liest und schickt genau eine Nachricht.
"""

import time

from slack_sdk.errors import SlackApiError

import slack_utils
from config import SLACK_TEST_USER_ID, slack

# Slack drosselt users_lookupByEmail. Ein Rate-Limit darf NICHT als "kein
# Slack-User" durchgehen — sonst meldet ausgerechnet die Prüfung, die Vertrauen
# schaffen soll, Leute als unerreichbar, die problemlos erreichbar sind.
MAX_VERSUCHE = 3
STANDARD_WARTEZEIT = 2


def _lookup(email):
    """(user_id, fehlercode). Bei Rate-Limit wird gewartet und neu versucht."""
    for versuch in range(MAX_VERSUCHE):
        try:
            return slack.users_lookupByEmail(email=email)["user"]["id"], None
        except SlackApiError as error:
            code = error.response.get("error")
            if code != "ratelimited":
                return None, code
            wartezeit = int(error.response.headers.get("Retry-After", STANDARD_WARTEZEIT))
            print(f"   ⏳ Slack drosselt — warte {wartezeit}s (Versuch {versuch + 1}).")
            time.sleep(wartezeit)
    return None, "ratelimited"


def pruefe(members):
    """Jedes Mitglied nachschlagen. Gibt (erreichbar, fehlend) zurück.

    `erreichbar` ist eine Liste von (member, user_id), `fehlend` eine Liste von
    (member, grund).
    """
    erreichbar, fehlend = [], []

    for member in members:
        if not member.get("email"):
            fehlend.append((member, "keine E-Mail und kein Komma im Namen"))
            continue

        user_id, fehler = _lookup(member["email"])
        if user_id:
            erreichbar.append((member, user_id))
        else:
            fehlend.append((member, fehler or "unbekannter Fehler"))

    return erreichbar, fehlend


def baue_bericht(erreichbar, fehlend):
    """Ergebnis als Slack-Nachricht."""
    gesamt = len(erreichbar) + len(fehlend)
    text = (
        f"🔎 *Tag-Prüfung* — {gesamt} Mitglieder mit losbarem Putzstatus\n"
        f"_(aktive Mitglieder mit abgeschlossenem Onboarding, deren Putzstatus "
        f"nicht „Ausgetragen\" ist — also auch „Neu\" und noch nicht gesetzte. "
        f"Bewusst mehr als der heutige Lostopf: wer heute „Neu\" ist, ist bald "
        f"„Normal\", und dann soll die Adresse schon stimmen.)_\n\n"
        f"✅ {len(erreichbar)} erreichbar   ❌ {len(fehlend)} nicht erreichbar\n"
    )

    if fehlend:
        text += "\n*Diese Leute bekämen produktiv keine DM:*\n"
        for member, grund in fehlend:
            quelle = member.get("email_quelle") or "keine"
            adresse = member.get("email") or "—"
            text += f"• *{member['name']}* — `{adresse}` ({quelle}): {grund}\n"
        text += (
            "\n_Fast immer die Lösung: `Interne Email` in der Mitgliederliste "
            "ausfüllen. Bei „abgeleitet\" hat der Bot die Adresse nur geraten._\n"
        )

    if erreichbar:
        # Als echte Erwähnungen, damit sichtbar ist, dass die Zuordnung stimmt.
        # In einer DM benachrichtigt das niemanden außer den Empfänger.
        geraten = [m for m, _ in erreichbar if m.get("email_quelle") == "abgeleitet"]
        text += f"\n*Erreichbar ({len(erreichbar)}):*\n"
        text += ", ".join(f"<@{uid}>" for _, uid in erreichbar)
        if geraten:
            text += (
                f"\n\n⚠️ Davon {len(geraten)} über eine *geratene* Adresse gefunden — "
                f"funktioniert, ist aber Zufall und kann jederzeit kippen: "
                + ", ".join(m["name"] for m in geraten)
            )

    return text


def run(members):
    """Prüfung ausführen und das Ergebnis als DM schicken."""
    if not SLACK_TEST_USER_ID:
        print(
            "❌ Der Modus 'tags' verschickt den Bericht per DM und braucht dafür "
            "SLACK_TEST_USER_ID. Ohne die Variable ist nicht festgelegt, wer ihn "
            "bekommt — Abbruch, statt jemanden Falsches anzuschreiben."
        )
        return 1

    print(f"\n🔎 Tag-Prüfung für {len(members)} Mitglieder mit losbarem Putzstatus")
    erreichbar, fehlend = pruefe(members)

    print(f"   ✅ {len(erreichbar)} erreichbar")
    for member, grund in fehlend:
        print(f"   ❌ {member['name']} ({member.get('email') or 'keine E-Mail'}): {grund}")

    # send_dm leitet über SLACK_TEST_USER_ID um; das Mitglied hier ist nur
    # Platzhalter für die Absenderzeile und wird nicht angeschrieben.
    slack_utils.send_dm(
        {"id": "tagcheck", "name": "Tag-Prüfung", "email": None},
        baue_bericht(erreichbar, fehlend),
    )
    return 0
