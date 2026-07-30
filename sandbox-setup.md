# Sandbox-Setup

Anleitung, um den Putzbot in einem Sandbox-Slack-Workspace zu testen, ohne echte Mitglieder anzuschreiben. Vorbereitung für Phase 7 aus [implementation-plan.md](implementation-plan.md).

## Warum überhaupt

Der Bot verschickt DMs an einzelne Mitglieder und postet in einen Kanal. Beides lässt sich nicht „halb" testen: entweder es geht raus oder nicht. Ein eigener Workspace trennt Testläufe sauber von echten Benachrichtigungen.

`DRY_RUN=true` bleibt trotzdem die erste Verteidigungslinie — damit läuft der komplette Ablauf durch (inkl. Auslosung und fertig formatierter Nachrichtentexte), es wird nur nichts geschrieben oder verschickt.

## Schritt 1: Slack-App im Sandbox-Workspace anlegen

1. Auf [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → *From scratch*.
2. Name z.B. „Putzbot (Sandbox)", als Workspace den Sandbox-Workspace wählen.
3. **OAuth & Permissions** → *Bot Token Scopes* hinzufügen:

   | Scope | wofür |
   |---|---|
   | `chat:write` | Nachrichten in Kanal und DMs |
   | `im:write` | DM-Konversation öffnen |
   | `users:read` | User-Liste |
   | `users:read.email` | E-Mail → Slack-User-ID (Kernstück des Mitglieder-Mappings) |
   | `reactions:read` | erst ab Phase 5/6 (✅/❌-Reaktionen), schadet aber nicht |

4. **Install to Workspace** → das **Bot User OAuth Token** (`xoxb-…`) kopieren. Das ist der `SLACK_TOKEN` für die Sandbox.
5. Im Sandbox-Workspace einen Kanal anlegen (z.B. `#putzbot-test`), den Bot per `/invite @Putzbot (Sandbox)` hinzufügen, und die Kanal-ID notieren (Kanal → Details → ganz unten).

## Schritt 2: Das E-Mail-Problem

Der Bot findet Mitglieder über ihre E-Mail-Adresse (`users_lookupByEmail`). Im Sandbox-Workspace gibt es die echten `@das-habitat.de`-Adressen aber nicht — jeder DM-Lookup würde scheitern.

Deshalb gibt es `SLACK_TEST_USER_ID`: ist die gesetzt, gehen **alle** DMs an diese eine Person, mit einem Vermerk, für wen sie eigentlich gedacht waren:

> _[Test-DM, eigentlich an Mustermann, Erika]_
>
> Hallo Erika! 🧹 …

So lässt sich der komplette Ablauf mit echten Notion-Daten testen, ohne dass jemand anderes etwas mitbekommt.

## Schritt 3: Notion

Zwei Möglichkeiten:

- **Nur lesen (empfohlen für den Anfang):** echte Notion-IDs verwenden, aber immer mit `DRY_RUN=true`. Es wird nichts geschrieben, du siehst aber die echte Auslosung mit echten Mitgliedern.
- **Auch schreiben:** Putzplan- und Mitglieder-Datenbank in einen Testbereich duplizieren, die Integration dort freigeben und `DS_A_ID`/`DS_B_ID`/`TEMPLATE_ID` auf die Kopien zeigen lassen. Nur so lassen sich Seitenerstellung und Status-Updates wirklich prüfen.

⚠️ Beim Duplizieren einer Notion-Datenbank werden Relationen **nicht** automatisch auf die Kopie umgebogen — nach dem Duplizieren prüfen, ob `Mitglieder` und `Putzplan` wirklich auf die jeweils andere Kopie zeigen und nicht noch auf das Original.

## Schritt 4: Lokal ausführen

Env-Variablen in der Shell setzen (PowerShell):

```bash
$env:NOTION_TOKEN="..."; $env:SLACK_TOKEN="xoxb-..."; $env:DS_A_ID="..."; $env:DS_B_ID="..."; $env:SLACK_CHANNEL_ID="..."; $env:TEMPLATE_ID="..."; $env:SLACK_TEST_USER_ID="U07UDK6V29F"; $env:DRY_RUN="true"; $env:DEBUG="true"; python main.py
```

Sinnvolle Reihenfolge beim Hochfahren:

1. `DRY_RUN=true`, `DEBUG=true` → nichts wird geschrieben, alles wird ausgegeben.
2. `DRY_RUN=false` mit `FORCE_PLAN=true` gegen die **Notion-Kopie** und den Sandbox-Kanal → prüft Seitenerstellung, Relationen und Status.
3. Erst danach echter Workspace (Phase 8).

`FORCE_PLAN=true` ist dabei wichtig: der Plan-Prozess läuft normalerweise nur in der letzten Woche eines Zyklus (aktuell KW 4, 8, 12, …), sonst müsstest du auf den richtigen Termin warten.

## Was ich von dir brauche, um mitzutesten

- [ ] `Jahr`-Property in der Putzplan-DB angelegt (+ bestehende Seiten mit 2026 befüllt) — ohne die schlagen alle Wochen-Lookups fehl.
- [ ] Sandbox-Kanal-ID und deine Slack-User-ID im Sandbox-Workspace (deine ID im echten Workspace ist `U07UDK6V29F`, im Sandbox-Workspace ist es eine andere).
- [ ] Ob du mit einer Notion-Kopie oder nur mit `DRY_RUN` gegen die echten Daten testen willst.
- [ ] Die Tokens **nicht** hier in den Chat — die gehören in deine Shell bzw. in die GitHub-Secrets.
