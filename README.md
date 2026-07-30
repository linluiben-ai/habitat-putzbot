# 🧹 Putzbot

Automatisiert den Putzplan des [Habitat](https://das-habitat.de): lost die wöchentliche Putzcrew aus, trägt sie in Notion ein und benachrichtigt sie per Slack.

Läuft unbeaufsichtigt über GitHub Actions — es gibt keinen Server.

## Wie es funktioniert

Das Jahr ist in **13 Zyklen à 4 Wochen** geteilt (Zyklus 1 = KW 1–4, …). In der letzten Woche eines Zyklus plant der Bot den **kompletten nächsten Zyklus** — vier Wochen Vorlauf, damit die Ausgelosten den Termin einplanen können.

Die Auslosung ist gestaffelt und wird erst gelockert, wenn zu wenige Kandidat:innen übrig sind:

1. Wer selten (≤1×) und lange nicht mehr geputzt hat
2. … dann ohne Rücksicht auf die Schonfrist
3. … dann mit höherer Einsatzzahl (bis maximal 3)

Wer eine Stufe früher qualifiziert war, behält seinen Platz. Angestrebt werden pro Woche 2 neue und 2 länger dabei seiende Mitglieder — damit man beim Putzen auch mal jemanden kennenlernt.

Ausgeloste bekommen eine DM und können mit ❌ reagieren, um zu tauschen. Der Bot fragt dann nach der Wunschwoche und trägt um.

## Zwei Abläufe

| Workflow | Wann | Was |
|---|---|---|
| [`monday_cleanup.yml`](.github/workflows/monday_cleanup.yml) | montags 08:00 UTC | Erinnerung an die aktuelle Woche; am Zyklusende zusätzlich Planung des Folgezyklus |
| [`poll_reactions.yml`](.github/workflows/poll_reactions.yml) | 5× täglich | schaut nach ✅/❌ auf den Auslos-DMs und wickelt Tauschwünsche ab |

Beide lassen sich in der Actions-Oberfläche manuell starten, inklusive Dry-Run- und Debug-Schalter.

## Lokal ausführen

```bash
python -m venv venv
venv/Scripts/pip install -r requirements.txt
cp .env.example .env    # ausfüllen
python main.py
```

Nützlichste Kombination zum Ausprobieren — kompletter Ablauf, aber nichts wird geschrieben oder verschickt:

```bash
DRY_RUN=true DEBUG=true FORCE_PLAN=true python main.py
```

Tests (ohne Netz und ohne Zugangsdaten):

```bash
python tests.py
```

## Wo was steht

| Datei | Inhalt |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Technische Übersicht: Module, Auslosungsregeln, Stolperfallen |
| [implementation-plan.md](implementation-plan.md) | Was gebaut ist, was noch offen ist, und **warum** die Regeln so sind |
| [roadmap.md](roadmap.md) | Ursprünglicher Entwurf + Ausblick (Buttons, Slash-Commands, …) |
| [sandbox-setup.md](sandbox-setup.md) | Testen ohne echte Mitglieder zu behelligen |
| [webhook-setup.md](webhook-setup.md) | Referenz für die Webhook-Variante (aktuell nicht genutzt) |

## Stand

V3 ist gebaut: Mehrwochen-Planung, faire gestaffelte Auslosung, wöchentliche Erinnerung und Tausch per Reaktion. Vor dem Produktivbetrieb steht noch der End-to-End-Test im Sandbox-Workspace — die offenen Punkte dafür stehen in [sandbox-setup.md](sandbox-setup.md).

Später geplant: Umzug auf den Hetzner-Server mit Socket Mode, dann Reaktionen in Sekunden statt Stunden und darauf aufbauend Buttons statt Emoji-Reaktionen.
