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
| Reschedule-Kapazität | **Harte Grenze bei 4.** Zielwoche mit weniger als 4 Leuten = ok, sonst abgelehnt mit Link zur Woche und Bitte, eine andere zu wählen. Der zwischenzeitlich angedachte weiche Puffer (5 = Crew fragen) ist wieder raus — viel Mechanik für einen Fall, der kaum eintritt, weil immer nur ein Zyklus im Voraus geplant wird und weiter entfernte Wochen praktisch leer sind. Steht als Idee im Feature-Tracker. |
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

## Phase 5 — Reaktionen per Polling (statt Webhook) ✅

**Entscheidung:** Kein Webhook-Server für V3. Der Bot fragt stattdessen mehrmals täglich bei Slack nach, ob jemand auf seine DMs reagiert hat. Begründung: Ausgelost wird 4 Wochen im Voraus, ein paar Stunden Reaktionszeit sind völlig ausreichend — und dafür entfallen Server, öffentliche URL, HTTPS und Hosting komplett. Läuft weiter auf GitHub Actions.

Der Umzug auf Socket Mode (dauerhafte WebSocket-Verbindung, Reaktionen in Sekunden) kommt mit dem Hetzner-Server, siehe Phase 9. Der Zustands-/Zuordnungsteil ist bei beiden Varianten identisch, der Wechsel betrifft nur die Zustellung.

- [x] Zuordnung DM ↔ (Mitglied, KW, Jahr) über **Slack-Message-Metadata** — kein externer Speicher nötig, die Info hängt an der Nachricht selbst.
- [x] Eigener Workflow `poll_reactions.yml`, 5× täglich zu Wachzeiten. Beide Workflows teilen sich eine `concurrency`-Group, damit nie zwei Läufe gleichzeitig schreiben.
- [x] `python main.py poll` als eigener Modus neben dem wöchentlichen Lauf.

## Phase 6 — `reschedule.py` ✅

- [x] ❌ auf der Auslos-DM → Bot fragt per DM nach der Zielwoche (Zahleneingabe).
- [x] Antwort des Mitglieds aus der DM-Historie lesen und validieren (existierende KW, in der Zukunft, innerhalb der nächsten 10 Zyklen, nicht gesperrt).
- [x] **Erst bei gültiger Antwort** wird umgetragen — bis dahin bleibt das Mitglied in seiner Woche, damit sie nicht unbesetzt dasteht, falls nie eine Antwort kommt (so steht es auch in [roadmap.md](roadmap.md)).
- [x] Kapazitätsprüfung der Zielwoche: weniger als 4 Leute = umtragen, sonst ablehnen und mit Link zur Woche erneut fragen.
- [x] Zielwoche anlegen, falls es noch keine Seite gibt.
- [x] Falls die alte Woche dadurch unterbesetzt ist: erneut auslosen, mit Ausschluss des gerade Ausgetragenen.
- [x] `RESCHEDULE_ENABLED = True` (schaltet den ❌-Hinweis in den DMs frei).

Noch nicht live verifiziert: der komplette Reaktions-Durchlauf (dafür fehlen die
DM-Scopes der Sandbox-App, siehe [sandbox-setup.md](sandbox-setup.md)). Die
Entscheidungslogik ist offline getestet.

## Phase 7 — End-to-End-Test im Sandbox-Workspace

Läuft über `.github/workflows/sandbox_test.yml` (nur manuell, `SANDBOX=true` und
`USE_TEST_DATA=true` fest verdrahtet statt als Input — der Workflow soll die
Produktivdaten strukturell nicht erreichen können). Braucht von den
Produktiv-Secrets nur `NOTION_TOKEN` und `DS_A_ID`.

- [x] Übergangsmodi `draw` und `plan`, damit Wochenauslosung und Zyklusplanung
      an verschiedenen Tagen laufen können (siehe Umstiegsplan unten).
- [x] DM-Zuordnung pro Mitglied (`reschedule.verlauf_fuer`): mit
      `SLACK_TEST_USER_ID` landen alle DMs im selben Kanal, ohne den Filter
      hätte ein einzelnes ❌ die ganze Wochencrew umgetragen.
- [ ] Kompletter Durchlauf: Plan → Raffle → DM → ❌ → Nachfrage → Antwort → Umtragen → Nachlosen → Remind.
- [ ] **Offen/blockiert:** `SANDBOX_SLACK_TOKEN` und `SANDBOX_SLACK_CHANNEL_ID`
      fehlen in den GitHub-Secrets (die übrigen fünf Werte kommen an). Ohne die
      bricht `config.py` ab — korrekt, aber der Testlauf kommt nicht los.
- [ ] Prüfen, ob Slack die Message-Metadata über `conversations_history`
      zurückgibt. `read_dm_history` gibt das bei `DEBUG=true` als Zeile
      „N Nachrichten, M vom Bot, K mit Metadata" aus.
- [ ] Fehlerfälle: zu wenige Kandidaten, Zielwoche voll (5 und ≥6), ungültige Antwort, Antwort auf eine gesperrte Woche, Jahreswechsel (KW 52 → KW 1), KW-53-Jahr.
- [ ] Prüfen, dass eine einmal verarbeitete Reaktion beim nächsten Poll nicht erneut greift.

## Umstiegsplan V2 → V3 (KW 32/33, 2026)

Der Wechsel passiert nicht an einem Tag, sondern in zwei Schritten — mit einer
Ankündigung dazwischen, damit die Auslos-DMs niemanden unvorbereitet treffen.
Beides wird **manuell** ausgelöst, die Cron-Trigger bleiben so lange aus.

| Wann | Aufruf | Was passiert |
|---|---|---|
| Mo, KW 32 | `python main.py draw` | KW-32-Seite anlegen, mit der neuen Auslosungslogik auf 4 auffüllen, **eine** Kanalnachricht. Keine DMs, kein Reschedule. |
| ~Mi, KW 32 | Ankündigung von Hand | Was sich mit V3 ändert (Zyklusplanung, DMs, Tausch per ❌). |
| danach | `python main.py plan` | Zyklus 9 (KW 33–36) nach dem neuen Verfahren, **mit** DMs und Reschedule. |
| danach | Actions wieder scharf | `monday_cleanup.yml` und `poll_reactions.yml` aktivieren. |

Wichtig: KW 32 ist die **letzte Woche von Zyklus 8**, `should_plan` ist dort also
`true`. Ein einfaches `python main.py` würde am Montag zusätzlich Zyklus 9 planen
und DMs verschicken — deshalb am Montag zwingend `draw` und nicht `weekly`.

## Phase 8 — Cutover

- [ ] Vorab einmal `DRY_RUN=true DEBUG=true` gegen den **echten** Slack-Workspace laufen lassen und die E-Mail→Slack-Zuordnung prüfen (im Sandbox lässt sich das nicht testen, weil dort alle DMs umgeleitet werden).
- [ ] Auf echten Workspace/Kanal + echte Notion-IDs umstellen.
- [ ] Sammelseiten „Ausgetragen" (KW 0) und „Postponed" (KW 54) in Notion löschen, jetzt wo `Putzstatus` sie ersetzt.
- [ ] Ersten vollen Zyklus eng beobachten.

## Phase 9 — Umzug auf Hetzner + Socket Mode

- [ ] Socket Mode statt Polling: dauerhafte WebSocket-Verbindung, Reaktionen in Sekunden statt Stunden. Braucht ein App-Level-Token (`xapp-…`) und einen dauerhaft laufenden Prozess — aber **keine** öffentliche URL, kein HTTPS, keinen Reverse Proxy.
- [ ] Der Zuordnungsteil aus Phase 5/6 bleibt unverändert; nur die Zustellung wechselt.
- [ ] Danach sind Buttons und Slash-Commands möglich (V3.2/V3.3, siehe [roadmap.md](roadmap.md)) — die gehen per Polling grundsätzlich nicht.
- [ ] [webhook-setup.md](webhook-setup.md) beschreibt die HTTP-Webhook-Variante. Die ist für diesen Fall vermutlich nicht mehr nötig; das Dokument bleibt als Referenz.

## Priorität, falls Zeit knapp ist

Phasen 1–4 liefern schon eigenständigen Mehrwert: korrekter Mehrwochen-Zyklus, fairere Auslosung, wöchentliche Erinnerung — nur ohne Reschedule. Phasen 5–6 sind mit dem Polling-Ansatz deutlich kleiner geworden und brauchen keine neue Infrastruktur.
