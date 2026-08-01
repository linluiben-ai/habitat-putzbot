# Webhook-Setup für Slack-Reaktionen (Häkchen/Kreuz)

Anleitung, um einen Webhook-Server aufzusetzen, der auf `reaction_added`-Events von Slack reagiert (für den `Reschedule`-Prozess aus [roadmap.md](roadmap.md)). Richtet sich an jemanden, der noch nie einen Server/Webhook betrieben hat.

## Warum das nötig ist

Der aktuelle Bot läuft als GitHub-Actions-Cronjob: er startet, macht seine Arbeit, beendet sich. Slack kann so einem Skript aber keine Nachricht schicken, wenn jemand Tage später auf eine DM reagiert — dafür braucht es einen Server, der dauerhaft (oder zumindest bei Bedarf) erreichbar ist und eine öffentliche HTTPS-URL hat, an die Slack das Event schickt.

**Empfehlung für den Start:** [Render.com](https://render.com), Free-Tier-Web-Service. Grund: Render führt eine ganz normale Flask-App via `gunicorn` aus — exakt das Setup, das später auf eurem Hetzner-Server laufen wird (dort dann via `systemd` statt Render). Es gibt also keinen Rewrite beim Umzug, nur einen Deploy-Ziel-Wechsel. Alternative wäre eine Serverless-Function (Vercel/Cloudflare), aber die läuft in einem anderen Ausführungsmodell (kein durchgehender Prozess) — das würde beim Umzug auf Hetzner eine Umschreibung erfordern.

⚠️ Der Free-Tier von Render schläft nach 15 Minuten Inaktivität und braucht dann ~30–50s zum Aufwachen. Slack erwartet aber eine Antwort innerhalb von 3 Sekunden. Für die Testphase ist das meist kein Problem (Slack toleriert einzelne Timeouts und retried), aber bevor das für echte Mitglieder scharf geschaltet wird, entweder auf einen bezahlten Render-Plan wechseln, einen Uptime-Ping-Dienst einrichten, oder direkt auf Hetzner umziehen.

## Schritt 1: Minimales Flask-Grundgerüst

Neue Datei (later, im Zuge der eigentlichen Implementierung) `webhook_app.py`:

```python
import os
from flask import Flask, request, jsonify

app = Flask(__name__)
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
seen_event_ids = set()  # simple in-memory Dedupe für Retries; reicht für den Start

@app.route("/slack/events", methods=["POST"])
def slack_events():
    payload = request.json

    # Slack schickt beim Einrichten der Subscription einen Verification-Handshake
    if payload.get("type") == "url_verification":
        return jsonify({"challenge": payload["challenge"]})

    event_id = payload.get("event_id")
    if event_id in seen_event_ids:
        return "", 200  # schon verarbeitet (Slack-Retry) -> ignorieren
    seen_event_ids.add(event_id)

    event = payload.get("event", {})
    if event.get("type") == "reaction_added":
        # TODO: hier reschedule.py aufrufen (async/schnell, wegen 3s-Limit)
        print(f"Reaction: {event.get('reaction')} von {event.get('user')}")

    return "", 200  # sofort ack'en, damit Slack nicht erneut sendet

if __name__ == "__main__":
    app.run(port=3000)
```

Wichtig: die Route antwortet sofort mit `200`, bevor die eigentliche Notion-Logik (Reschedule) fertig ist — sonst laufen die 3 Sekunden ab und Slack schickt das Event erneut.

## Schritt 2: Bei Render deployen

1. Auf [render.com](https://render.com) mit dem GitHub-Account einloggen, Zugriff auf dieses Repo erlauben.
2. "New" → "Web Service" → dieses Repo auswählen.
3. Build Command: `pip install -r requirements.txt` (bzw. eine eigene `requirements.txt` im Webhook-Ordner, falls getrennt).
4. Start Command: `gunicorn webhook_app:app` (Gunicorn zu den Requirements hinzufügen).
5. Environment: die benötigten Secrets eintragen (`NOTION_TOKEN`, `SLACK_TOKEN`, `SLACK_SIGNING_SECRET`, `DS_A_ID`, `DS_B_ID`, …) — genau wie bei den GitHub-Actions-Secrets, nur eben bei Render statt GitHub.
6. Deployen. Render gibt euch eine URL wie `https://putzbot-webhook.onrender.com`.

## Schritt 3: Slack App konfigurieren

1. Auf [api.slack.com/apps](https://api.slack.com/apps) die bestehende Putzbot-App öffnen (die, deren Token in `SLACK_TOKEN` steckt).
2. **OAuth & Permissions** → unter "Bot Token Scopes" sicherstellen, dass mindestens vorhanden sind: `reactions:read`, `im:history`, `im:write`, `users:read.email`, `chat:write` (die letzten beiden sind vermutlich schon da).
3. **Event Subscriptions** → aktivieren.
4. Request URL: `https://putzbot-webhook.onrender.com/slack/events`. Slack schickt sofort den Verification-Handshake (`url_verification`) — die App muss dafür schon live sein (Schritt 2 zuerst!), sonst schlägt die Verifizierung fehl.
5. Unter "Subscribe to bot events" → `reaction_added` hinzufügen.
6. Speichern. Falls Scopes neu hinzugefügt wurden, muss die App neu in den Workspace installiert werden (Slack fragt danach von selbst).
7. Unter **Basic Information** → "App Credentials" das **Signing Secret** kopieren → als `SLACK_SIGNING_SECRET` bei Render hinterlegen (wird für die Verifizierung eingehender Requests gebraucht, sonst könnte theoretisch jeder beliebige Payloads an die URL schicken).

## Schritt 4: End-to-End testen

1. `python test_pm.py` (mit `TEST_EMAIL` auf die eigene Adresse gesetzt) → eigene Test-DM vom Bot erhalten.
2. Mit ✅ oder ❌ reagieren.
3. In den Render-Logs (Dashboard → "Logs") nachschauen, ob das `reaction_added`-Event ankommt und mit dem `print(...)` aus Schritt 1 geloggt wird.
4. Erst danach die eigentliche `reschedule.py`-Logik anbinden (siehe [implementation-plan.md](implementation-plan.md)).

## Später: Umzug auf Hetzner

Wenn der Webhook-Server stabil läuft, kann exakt dieselbe Flask-App auf dem Hetzner-Server laufen:
- App-Code unverändert übernehmen.
- `gunicorn webhook_app:app` per `systemd`-Service dauerhaft laufen lassen (kein Cold-Start-Problem mehr).
- Ein Reverse Proxy (z.B. `nginx` oder `caddy`) für HTTPS davor schalten (Slack verlangt HTTPS).
- In der Slack-App-Konfiguration nur die Request-URL auf die neue Adresse ändern.
