# Implementation-Plan: Putzbot V3

Reihenfolge/Checkliste, um von der heutigen Single-File-V2 zum in [roadmap.md](roadmap.md) beschriebenen Mehrwochen-Zyklus mit Reschedule-Flow zu kommen. Jede Phase soll für sich funktionsfähig/deploybar sein — nicht alles auf einmal umbauen.

## Geklärte Entscheidungen

Stand der Abstimmung, gilt als verbindlich für die Implementierung:

| Thema | Entscheidung |
|---|---|
| Zyklus-Anker | Zyklus 1 = KW 1–4, … Zyklus 13 = KW 49–52. KW 53 (in manchen ISO-Jahren) zählt zu Zyklus 13, eröffnet keinen neuen. |
| Jahres-Eindeutigkeit | Neue Property **`Jahr` (number)** in der Putzplan-DB. Bot schreibt sie beim Anlegen, alle Lookups filtern auf `Kalenderwoche` + `Jahr`. |
| `Putzstatus` (Mitgliederliste) | Wählbar sind **nur `Normal` und leer**. `Ausgetragen`, `Neu`, `Priorität` und `Postponed` fliegen raus. (Sonderbehandlung von `Priorität`/`Postponed` evtl. später.) |
| ❓-Icon | Entfällt — wird durch `Putzstatus` ersetzt. |
| `min_size` | Entfällt. Alles läuft über `needed` = Zielgröße (4) − bereits für die Woche eingetragene Mitglieder. |
| Putzhäufigkeit | Gestaffelt: zuerst nur Mitglieder mit ≤1 Putzeinsatz, dann ≤2, dann ≤3. **Obergrenze 3.** |
| Aktualität | Wer in den letzten 3 Zyklen (12 Wochen) geputzt hat, kommt erst in den Fallback-Stufen in den Topf. |
| Alt/Neu | „Neu" = Eintrittsdatum < 1 Jahr her. Ziel 2 neue + 2 alte pro Woche, aber **weichstes Kriterium** — wird in `raffle.py` behandelt, nicht im Pool-Bau. |
| Fallback-Fairness | Wer **vor** einer Fallback-Lockerung schon im Topf war, wird garantiert gezogen; nur die Restplätze werden mit gelockerten Kriterien besetzt. |
| Reschedule-Kapazität | 1–4 Mitglieder = ok · 5 = Crew wird gefragt, ob jemand tauschen will · ab 6 = Zielwoche wird abgelehnt. |
| Reschedule-Lookup | Läuft immer `Notion Lookup` für alte + neue Woche (auch um die Belegung zu prüfen und die Seite ggf. anzulegen). |
| Reaktionen | Ausgeloste Mitglieder stehen **von Anfang an** in ihrer Woche. Nur ❌ trägt sie wieder aus. |
| Erinnerungen/Fristen | Kein Auto-Confirm, keine Deadline in V3. Vertagt auf **V3.1** (Feature-Tracker-DB `2f6b71ac7d098024af8bd0059351cd87`). |
| Testing | Erst Sandbox-Slack-Workspace aufsetzen, dann dort testen. Kein Live-Test mit echten Mitgliedern vorher. |

## Reale Notion-Schemas (per Connector verifiziert)

**Mitgliederliste** — `collection://32b442c0-9a5c-4666-9f78-6647909752b8` (= `DS_A_ID`)
`Name, Vorname` (title, Format „Nachname, Vorname") · `Eintrittsdatum` (date) · `Austrittsdatum` (date) · `E-Mail`, `Interne Email` (email) · `Mitgliedsstatus` (multi_select) · `Onboarding: Status` (select) · **`Putzstatus`** (select: `Ausgetragen`/`Priorität`/`Postponed`/`Normal`/`Neu`) · `Putzplan` (relation → Putzplan) · `Putzanzahl` (rollup, count)

**Putzplan** — `collection://2eab71ac-7d09-8055-9bf6-000bb4351efb` (= `DS_B_ID`)
`Titel` (title) · `Kalenderwoche` (number) · `Mitglieder` (relation → Mitgliederliste) · `Anzahl Mitglieder` (rollup) · `Status` (status: `Geplant`/`Crew voll`/`Nicht auswählen`/`Erledigt`) · `Archiv` (checkbox) · **kein Jahr** (→ wird ergänzt, s.o.)
Templates: „Neue Putzcrew (Automation)" `2eab71ac-7d09-80ef-954f-d3e298915dfe` · „Putzcrew KW " (default) `2f3b71ac-7d09-8090-a23b-d382f6fa64d5`

### Dabei gefundene Bugs in V2

- **Kein Jahresfilter** beim KW-Lookup → im Januar kann die Seite des Vorjahres mit derselben KW getroffen werden. Wird durch die `Jahr`-Property behoben.
- **Keine Pagination** bei den Notion-Queries (`has_more`/`next_cursor` werden ignoriert). Bei ~80 Mitgliedern geht das noch gut, ab 100 werden Mitglieder stillschweigend übersehen.
- **`Archiv` und `Status: Nicht auswählen` werden ignoriert** — archivierte bzw. bewusst gesperrte Wochen können getroffen/befüllt werden.

## Phase 0 — Vorbereitung (manuell, blockiert Phase 2+)

- [ ] Property **`Jahr` (number)** in der Putzplan-DB anlegen.
- [ ] Bestehende Putzplan-Seiten mit `Jahr` backfillen (alle bisherigen dürften 2026 sein).
- [ ] Sandbox-Slack-Workspace aufsetzen (siehe [sandbox-setup.md](sandbox-setup.md)).
- [ ] Prüfen, ob `TEMPLATE_ID` auf „Neue Putzcrew (Automation)" zeigt.

## Phase 1 — Refactor zu Mehrdatei-Struktur ✅

- [x] `config.py`, `cycles.py`, `notion.py`, `raffle.py`, `slack_utils.py`, `scheduler.py` aus [main.py](main.py) herausgezogen.
- [x] `main.py` orchestriert nur noch.
- [x] `monday_cleanup.yml` behält `python main.py` als Einstiegspunkt.
- [x] Pagination in allen Notion-Queries ergänzt.
- [x] `DRY_RUN` überarbeitet (läuft jetzt den **ganzen** Flow durch und überspringt nur die Schreibzugriffe) + neues `DEBUG` für Detail-Diagnostik.

## Phase 2 — Candidate-Pool & Raffle ✅

- [x] `Putzstatus`-Filter ersetzt den ❓-Icon-Check.
- [x] Gestaffelte Pool-Bildung (≤1/≤2/≤3 Einsätze × Aktualität) mit Locking der jeweils strengeren Stufe.
- [x] Alt/Neu-Balance (2+2) in `raffle.py`, unter Berücksichtigung der schon eingetragenen Mitglieder.

## Phase 3 — `scheduler.py` (Plan-Prozess) ✅

- [x] Zyklus-Mathematik inkl. KW 53 und Jahreswechsel (`cycles.py`).
- [x] Plan-Lauf in der letzten Woche eines Zyklus: Schleife über die 4 Wochen des Folgezyklus, Seite anlegen falls nötig, `Raffle` falls unterbesetzt.
- [x] Wochen mit `Status: Nicht auswählen` oder `Archiv: true` werden übersprungen.
- [x] DMs an neu ausgeloste Mitglieder (❌-Hinweis erst aktiv, wenn `RESCHEDULE_ENABLED`).

## Phase 4 — Remind-Prozess ✅

- [x] Wöchentliche Erinnerung mit @-Erwähnungen der Crew in den Zielkanal.
- [x] Läuft jeden Montag, unabhängig vom Plan-Lauf.

## Phase 5 — Webhook-Service

- [ ] [webhook-setup.md](webhook-setup.md) Schritte 1–4 durchgehen (Flask, Render-Deploy, Slack-Event-Subscription, End-to-End bis Log-Print).
- [ ] Erst wenn Reaktionen zuverlässig ankommen, weiter zu Phase 6.

## Phase 6 — `reschedule.py`

- [ ] Mapping DM-Message-`ts` → (Mitglied, KW, Jahr) persistieren, damit der Webhook die Reaktion zuordnen kann.
- [ ] ❌ → Mitglied aus der Woche austragen, per PM nach Zielwoche fragen (Zahleneingabe), Validierung „innerhalb der nächsten 10 Zyklen".
- [ ] Kapazitätsprüfung der Zielwoche (1–4 / 5 / ≥6, s.o.) und Anlegen der Zielwoche falls nicht vorhanden.
- [ ] Falls alte Woche dadurch unterbesetzt: `Raffle` für sie erneut, mit Ausschluss des gerade ausgetragenen Mitglieds.
- [ ] `RESCHEDULE_ENABLED = True` setzen (schaltet den ❌-Hinweis in den DMs frei).

## Phase 7 — End-to-End-Test im Sandbox-Workspace

- [ ] Kompletter Durchlauf: Plan → Raffle → DM → Reaktion → Reschedule → Nachlosen → Remind.
- [ ] Fehlerfälle: zu wenige Kandidaten, Zielwoche voll (5 und ≥6), Jahreswechsel (KW 52 → KW 1), KW-53-Jahr.

## Phase 8 — Cutover

- [ ] Auf echten Workspace/Kanal + echte Notion-IDs umstellen.
- [ ] Ersten vollen Zyklus eng beobachten.

## Phase 9 — Später

- [ ] Webhook-Umzug auf Hetzner (siehe Ende von [webhook-setup.md](webhook-setup.md)) — reiner Deploy-Wechsel, kein Rewrite.
- [ ] V3.1: Erinnerungen/Fristen für ausstehende Reaktionen.
- [ ] Ggf. Sonderbehandlung `Putzstatus: Priorität` / `Postponed`.

## Priorität, falls Zeit knapp ist

Phasen 1–4 liefern schon eigenständigen Mehrwert **ohne** Webhook: korrekter Mehrwochen-Zyklus, fairere Auslosung, wöchentliche Erinnerung. Nur Reschedule fehlt dann. Phasen 5–6 sind der aufwändigere, unabhängig nachziehbare Teil.
