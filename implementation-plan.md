# Implementation-Plan: Putzbot V3

Reihenfolge/Checkliste, um von der heutigen Single-File-V2 ([main.py](main.py)) zum in [roadmap.md](roadmap.md) beschriebenen Mehrwochen-Zyklus mit Reschedule-Flow zu kommen. Jede Phase soll für sich funktionsfähig/deploybar sein — nicht alles auf einmal umbauen.

## Offene Fragen (vor bzw. während Phase 2/6 klären)

Diese sind bei der Durchsicht von [roadmap.md](roadmap.md) aufgefallen und beeinflussen die jeweilige Phase direkt. Bis sie geklärt sind, stehen hier die Annahmen, mit denen weitergeplant wird:

1. **Zyklus-Anker:** Zyklus 1 = KW 1–4, Zyklus 13 = KW 49–52; KW 53 (kommt in manchen Jahren vor) zählt zum letzten Zyklus des Jahres statt einen neuen zu öffnen.
2. **Alt/Neu-Kandidatenpool:** "alt" = länger nicht geputzt (Putzcounter = Zyklen seit letztem Putzen), "neu" = noch nie geputzt. Der Putzcounter wird hochgezählt, bis genug Kandidaten da sind, aber gedeckelt (Abbruch + Warnung, wenn der Counter die gesamte Mitgliederzahl überschreitet, statt endlos zu laufen). **Bitte bestätigen/korrigieren**, bevor `raffle.py` (Phase 2) geschrieben wird.
3. **Reschedule-Zielwoche voll:** Wird blockiert (Mitglied wird gebeten, eine andere Woche zu wählen), statt die Woche zu überfüllen.
4. **Reschedule-Zielwoche existiert noch nicht:** Wird per `Notion Lookup` + Seitenerstellung (wie im `Plan`-Prozess) nachgeholt.
5. **Nachlosen nach Absage:** Das Mitglied, das gerade abgesagt hat, wird explizit aus dem Kandidatenpool für die Nachlosung seiner alten Woche ausgeschlossen.
6. **`Putzstatus`-Property:** Klären, ob das eine neue Notion-Property ist (Ersatz für den ❓-Icon-Hack) oder ob `roadmap.md` hier nur den Icon-Mechanismus meint.
7. **Kein Reaction innerhalb der Frist:** Noch nicht spezifiziert. Muss vor Phase 6 (Reschedule-Logik) entschieden werden — z.B. stiller Auto-Confirm, erneute Erinnerung, oder bewusst out-of-scope für V3.

## Phase 0 — Vorbereitung

- [ ] Offene Fragen oben klären (mindestens 2, 6, 7 — die anderen haben brauchbare Default-Annahmen).
- [ ] Falls nötig: neue Notion-Property(s) anlegen (z.B. `Putzstatus`, falls Frage 6 das ergibt).
- [ ] Fixieren, was "Zyklus 1" ist (Kalenderjahr-Start, siehe Frage 1) — als Konstante, nicht implizit im Code verstreut.

## Phase 1 — Refactor zu Mehrdatei-Struktur (kein Verhaltenswechsel)

- [ ] `config.py`, `notion.py`, `raffle.py`, `slack_utils.py` aus dem heutigen [main.py](main.py) extrahieren, 1:1 gleiches Verhalten (inkl. `DRY_RUN`).
- [ ] `main.py` ruft nur noch die Module auf, keine Business-Logik mehr direkt darin.
- [ ] `monday_cleanup.yml` unverändert lassen (`python main.py` bleibt der Einstiegspunkt) — nur intern refactored.
- [ ] Verifizieren: `DRY_RUN=true python main.py` liefert exakt dieselbe Kandidatenliste wie vor dem Refactor.

## Phase 2 — Candidate-Pool-Logik erweitern (`raffle.py`)

- [ ] `build_candidate_pool` gemäß geklärter Frage 2 implementieren (alt/neu-Split, expandierender Putzcounter mit Obergrenze).
- [ ] Alte binäre `has_cleaned`-Logik (`len(putz_rel) > 0`) ablösen.
- [ ] Testen mit `DRY_RUN`, dass die Kandidatenliste für die aktuelle Woche sich sinnvoll verhält (Stichprobe von Hand gegenprüfen).

## Phase 3 — `scheduler.py` (Plan-Prozess)

- [ ] Funktion, die für eine gegebene KW ermittelt: ist das die letzte Woche eines Zyklus?
- [ ] Wenn ja: Schleife über die 4 Wochen des nächsten Zyklus, pro Woche `Notion Lookup` + ggf. Seite erstellen + ggf. `Raffle` auslösen.
- [ ] `main.py` (Cron-Entrypoint) so anpassen, dass montags immer geprüft wird, ob `scheduler.py` laufen soll (siehe Frage/Annahme 2 oben aus der Architektur-Diskussion: Plan+Raffle nur in der letzten Zyklus-Woche, sonst nur Remind).

## Phase 4 — Remind-Prozess

- [ ] Eigene Funktion/Modul (oder Teil von `slack_utils.py`): holt aktuelle Woche per `Notion Lookup`, baut Standardnachricht mit @-Erwähnung der eingetragenen Mitglieder, postet in den Zielkanal.
- [ ] In `main.py` verdrahten: läuft **jeden** Montag, unabhängig davon ob Plan/Raffle diese Woche laufen.
- [ ] Testen im Test-Channel (`C0A9DTJLFRU`) vor dem Umstellen auf den echten Kanal.

## Phase 5 — Webhook-Service (Grundgerüst, ohne echte Reschedule-Logik)

- [ ] Schritte aus [webhook-setup.md](webhook-setup.md) 1–4 durchgehen: Flask-App, Render-Deploy, Slack-App-Konfiguration, End-to-End-Test bis zum reinen Log-Print.
- [ ] Erst wenn Reaktionen zuverlässig im Render-Log ankommen, weiter zu Phase 6.

## Phase 6 — `reschedule.py`

- [ ] Mapping DM-Message-Timestamp → (Mitglied, KW_alt) muss irgendwo gespeichert werden, damit der Webhook beim Reaction-Event weiß, wer/welche Woche gemeint ist (z.B. als Notion-Property auf der Mitglieder- oder Wochen-Seite, oder eine kleine eigene Tabelle — noch offen, siehe Frage 7 mit verwandten Anforderungen).
- [ ] Bot fragt per PM nach Zielwoche (Zahleneingabe gemäß Roadmap) — Validierung: liegt in den nächsten 10 Zyklen.
- [ ] Zielwoche-Kapazitätscheck (Annahme 3), Zielwoche-Existenzcheck (Annahme 4).
- [ ] Mitglied aus alter Woche austragen, in neue eintragen.
- [ ] Falls alte Woche dadurch < 4 Mitglieder: `Raffle` für die alte Woche auslösen, mit Ausschluss des gerade ausgetragenen Mitglieds (Annahme 5).
- [ ] `webhook_app.py` verdrahten: `reaction_added` → `reschedule.py` statt nur Log-Print.

## Phase 7 — End-to-End-Test

- [ ] Kompletter Durchlauf im Test-Channel/mit Test-Mitgliedern: Plan → Raffle → DM → Reaction → Reschedule → Re-Raffle der alten Woche → Remind.
- [ ] Absichtlich Fehlerfälle durchspielen: zu wenige Kandidaten im Pool, Zielwoche voll, keine Reaction innerhalb der Frist (sobald Frage 7 geklärt ist).

## Phase 8 — Cutover

- [ ] `monday_cleanup.yml` (oder neuer Workflow-Name) auf den echten Slack-Kanal/echte Notion-IDs umstellen.
- [ ] Ersten vollen Zyklus eng beobachten (Logs, Slack-Nachrichten stichprobenartig prüfen).

## Phase 9 — Später: Umzug Webhook-Service auf Hetzner

- [ ] Siehe letzter Abschnitt in [webhook-setup.md](webhook-setup.md) — reiner Deploy-Ziel-Wechsel, kein Code-Rewrite nötig, wenn Phase 5 wie beschrieben mit Flask/gunicorn umgesetzt wurde.

## Priorität, falls Zeit knapp ist

Phasen 1–4 (Refactor, bessere Candidate-Pool-Logik, Plan/Remind-Trennung) liefern bereits eigenständigen Mehrwert **ohne** den Webhook-Server — der Bot lost dann einfach weiterhin ohne Reschedule-Möglichkeit, aber mit korrektem Mehrwochen-Zyklus und wöchentlicher Erinnerung. Phasen 5–6 (Webhook + Reschedule) sind der aufwändigere, unabhängig nachziehbare Teil.
