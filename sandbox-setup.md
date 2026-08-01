# Sandbox-Setup

Anleitung, um den Putzbot in einem Sandbox-Slack-Workspace zu testen, ohne echte Mitglieder anzuschreiben. Vorbereitung für Phase 7 aus [implementation-plan.md](implementation-plan.md).

## Warum überhaupt

Der Bot verschickt DMs an einzelne Mitglieder und postet in einen Kanal. Beides lässt sich nicht „halb" testen: entweder es geht raus oder nicht. Ein eigener Workspace trennt Testläufe sauber von echten Benachrichtigungen.

`DRY_RUN=true` bleibt trotzdem die erste Verteidigungslinie — damit läuft der komplette Ablauf durch (inkl. Auslosung und fertig formatierter Nachrichtentexte), es wird nur nichts geschrieben oder verschickt.

## Schritt 1: Slack-App im Sandbox-Workspace anlegen

Per **App-Manifest**, nicht Klick für Klick:

1. Auf [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → *From an app manifest*.
2. Sandbox-Workspace wählen, dann den Inhalt von [slack-app-manifest.yml](slack-app-manifest.yml) reinkopieren.
3. **Install to Workspace** → das **Bot User OAuth Token** (`xoxb-…`) kopieren. Das gehört in `SANDBOX_SLACK_TOKEN`.

   ⚠️ Slack zeigt unter Umständen **zwei** Tokens an — nicht verwechseln:

   | Token | Wo | Wofür |
   |---|---|---|
   | **Bot User OAuth Token** `xoxb-…` | OAuth & Permissions | Alle Web-API-Aufrufe des Bots: Nachrichten posten, DMs öffnen, E-Mail→User-ID. **Das ist der, den der Bot braucht.** |
   | **App-Level Token** `xapp-…` | Basic Information → App-Level Tokens | Nur für Socket Mode und ein paar org-weite APIs. Wird hier aktuell **nicht** gebraucht. |
4. Im Sandbox-Workspace einen Kanal anlegen (z.B. `#putzbot-test`), den Bot per `/invite @Putzbot` hinzufügen, und die Kanal-ID notieren (Kanal → Details → ganz unten).

Die Scopes stehen alle im Manifest, inklusive derer für Phase 5/6 (`reactions:read`, `im:history`) — die schaden jetzt nicht und ersparen später eine Neuinstallation der App.

**Slack CLI lohnt sich hier nicht.** Die ist auf Deno-basierte Workflow-Apps ausgelegt; für einen klassischen Bot mit Token käme man über Umwege zum selben Ergebnis. Das Manifest bringt den eigentlichen Vorteil (reproduzierbar, alle Scopes auf einmal) ganz ohne Installation.

## Schritt 2: Das E-Mail-Problem

Der Bot findet Mitglieder über ihre E-Mail-Adresse (`users_lookupByEmail`). Im Sandbox-Workspace gibt es die echten `@das-habitat.de`-Adressen aber nicht — jeder DM-Lookup würde scheitern.

Deshalb gibt es `SLACK_TEST_USER_ID`: ist die gesetzt, gehen **alle** DMs an diese eine Person, mit einem Vermerk, für wen sie eigentlich gedacht waren:

> _[Test-DM, eigentlich an Mustermann, Erika]_
>
> Hallo Erika! 🧹 …

So lässt sich der komplette Ablauf mit echten Notion-Daten testen, ohne dass jemand anderes etwas mitbekommt.

## Schritt 3: Notion

Wichtig vorweg: **der Bot schreibt ausschließlich in die Putzplan-DB.** Die Mitgliederliste wird nur gelesen. Eine Kopie der Mitgliederliste braucht es zum Testen also gar nicht — nur eine Kopie des Putzplans.

Zwei Stufen:

- **Nur lesen (empfohlen für den Anfang):** echte Notion-IDs, aber `DRY_RUN=true`. Die Auslosung läuft mit echten Mitgliedern und echter Historie durch, es wird nur nichts geschrieben. Realistischstes Bild der Fairness-Logik bei null Risiko.
- **Auch schreiben:** nur die **Putzplan**-DB duplizieren, die Integration darauf freigeben, und `USE_TEST_DATA=true` mit `TEST_DS_B_ID` + `TEST_TEMPLATE_ID` setzen. `TEST_DS_A_ID` kann leer bleiben — dann wird die echte Mitgliederliste gelesen.

### Putzplan duplizieren

1. Putzplan-DB öffnen → `⋯` → **Duplicate** (mit Inhalt, damit Views und Templates mitkommen).
2. Kopie an einen privaten Ort verschieben und eindeutig benennen, z.B. „🧪 Putzplan (Test)".
3. **Die Kopie für die Notion-Integration freigeben**: auf der Seite `⋯` → *Connections* → die Putzbot-Integration hinzufügen. Wird das vergessen, sieht der Bot die Datenbank schlicht nicht — häufigste Ursache für ein stilles „0 Seiten geladen".
4. In der Kopie nachsehen, wie die `Mitglieder`-Relation heißt und wohin sie zeigt.

**Zur Rückrelation:** Notion legt für die Kopie eine **zweite** Relations-Property auf der Mitgliederliste an (z.B. `Putzplan (Test)`) — die echte `Putzplan`-Property bleibt davon unberührt. Testläufe können den Produktivbetrieb also nicht durcheinanderbringen; es taucht lediglich eine zusätzliche Spalte in der Mitgliederliste auf.

Damit der Bot beim Testen die *richtige* Historie liest, muss er den Namen dieser zweiten Property kennen:

```
PUTZPLAN_RELATION_PROP=Putzplan (Test)
```

Ohne das liest er weiter die echte `Putzplan`-Relation, deren Seiten-IDs in der Testdatenbank nicht existieren — dann wirkt jede:r wie „noch nie geputzt" und jeder Testlauf startet bei null.

Die vorhandene Kopie „Mitgliederliste (Testdatenbank, inoffiziell!)" stammt aus der Zeit vor `Putzstatus`, `Putzplan` und `Interne Email` — ohne diese drei Properties läuft der Bot dagegen nicht. Am einfachsten ignorieren.

## Schritt 4: Die Betriebsmodi

Vier unabhängige Schalter, beliebig kombinierbar:

| Schalter | Was er tut | Was er **nicht** tut |
|---|---|---|
| `DRY_RUN=true` | Lässt den kompletten Ablauf laufen: Wochen-Lookup, Kandidatenpool, Auslosung, fertig formatierte Nachrichtentexte. Jeder Schreibzugriff wird stattdessen als `[DRY RUN] würde …` ausgegeben. | Ändert nichts in Notion, verschickt nichts in Slack. |
| `DEBUG=true` | Zusätzliche Diagnosezeilen: wie viele Seiten je Query geladen wurden, wie groß der Kandidatenpool auf **jeder** Fallback-Stufe ist, welche Stufe am Ende gezogen hat, warum eine Seite ignoriert wurde. | Ändert am Verhalten nichts — reine Ausgabe. |
| `FORCE_PLAN=true` | Erzwingt die Zyklusplanung, egal welche KW gerade ist. | Ändert nicht, *welcher* Zyklus geplant wird — immer der auf die aktuelle Woche folgende. |
| `USE_TEST_DATA=true` | Schaltet Putzplan-DB und Template auf die Testkopien um (`TEST_DS_B_ID`, `TEST_TEMPLATE_ID`). | Schaltet Slack **nicht** um. |
| `SANDBOX=true` | Schaltet Token, Kanal und DM-Ziel auf den Sandbox-Workspace um (`SANDBOX_SLACK_*`). | Schaltet Notion **nicht** um. |

`SANDBOX` und `USE_TEST_DATA` sind absichtlich getrennt: die nützlichste Kombination ist oft Sandbox-Slack **mit** echten Notion-Daten im Dry Run — echte Auslosung sehen, ohne dass jemand etwas mitbekommt. Beide brechen ab, wenn ihre Pflichtwerte fehlen, statt still auf Produktiv zurückzufallen.

Beim Start zeigt der Bot in Zeile 2, wohin er zeigt:

```
🤖 Putzbot — KW 31/2026 (Zyklus 8)
   Notion: 🧪 TESTKOPIE   Slack: 🧪 SANDBOX
```

Ohne `FORCE_PLAN` passiert bei einem Testlauf mitten im Zyklus fast nichts: der Bot postet nur die Wochenerinnerung und meldet „kein Plan-Lauf". Zum Testen der Auslosung brauchst du ihn also fast immer.

`DRY_RUN` und `FORCE_PLAN` zusammen sind die nützlichste Kombination: du siehst die vollständige Auslosung für den nächsten Zyklus, ohne dass irgendetwas passiert.

Zusätzlich lenkt `SLACK_TEST_USER_ID` alle DMs auf dich um (siehe Schritt 2).

## Schritt 5: Lokal ausführen

Alle Werte kommen in eine `.env` neben `config.py` — die ist in `.gitignore` und wird automatisch geladen. [.env.example](.env.example) als Vorlage kopieren und ausfüllen:

```bash
cp .env.example .env
```

Dann reicht:

```bash
python main.py
```

Echte Umgebungsvariablen haben Vorrang vor der Datei — die GitHub-Action-Secrets bleiben davon also unberührt, und einzelne Werte lassen sich für einen Lauf überschreiben, ohne die Datei anzufassen.

Sinnvolle Reihenfolge beim Hochfahren:

1. `DRY_RUN=true DEBUG=true FORCE_PLAN=true` gegen die **echten** Daten → zeigt die echte Auslosung, schreibt nichts.
2. Dasselbe ohne `DRY_RUN`, dafür mit `USE_TEST_DATA=true` und Sandbox-Kanal → prüft Seitenerstellung, Relationen und Status.
3. Erst danach der echte Workspace (Phase 8).

Beim Start gibt der Bot in den ersten Zeilen aus, welche Datenquelle und welche Modi aktiv sind — ein Blick dorthin, bevor du dich über das Ergebnis wunderst.

## Die Fake-User im Sandbox-Workspace

Ein Slack-Sandbox-Workspace bringt ein paar vorgefertigte User mit. Wofür sie taugen:

- ✅ **DM-Zustellung testen** — der Bot kann ihnen schreiben.
- ✅ **Kanal-Erwähnungen testen** — sie tauchen als echte `<@U…>`-Mentions auf.
- ❌ **Reaktionen testen** — dafür müsste man sich als sie einloggen, was nicht geht. Das ✅/❌ aus Phase 6 musst du an einer DM an dich selbst testen.
- ❌ **E-Mail-Lookup testen** — ihre Adressen stehen nicht in Notion, `users_lookupByEmail` findet sie also nicht. Genau dafür gibt es `SLACK_TEST_USER_ID`.

Kurz: nützlich als Kulisse, aber der eigentliche Reaktions-Flow läuft über dich selbst.

## Testlauf über GitHub Actions

Neben dem lokalen Aufruf gibt es [`sandbox_test.yml`](.github/workflows/sandbox_test.yml)
— nur manuell startbar, mit `SANDBOX=true` und `USE_TEST_DATA=true` **fest verdrahtet**
statt als Input. Der Workflow soll die Produktivdaten auch bei einem Fehlklick nicht
erreichen können; wer produktiv laufen will, nimmt die anderen beiden Workflows.

Praktischer Nebeneffekt: weil `config.py` im Sandbox-Modus `SLACK_TOKEN`,
`SLACK_CHANNEL_ID`, `DS_B_ID` und `TEMPLATE_ID` ohnehin ersetzt, braucht dieser Lauf von
den Produktiv-Secrets nur `NOTION_TOKEN` und `DS_A_ID` — die Mitgliederliste wird
ausschließlich gelesen. Ein gelöschter Produktions-`SLACK_TOKEN` stört ihn nicht.

Benötigte Secrets (alternativ als Repository-Variables):

| Name | Zwingend | Wofür |
|---|---|---|
| `NOTION_TOKEN`, `DS_A_ID` | ja | Mitgliederliste lesen |
| `SANDBOX_SLACK_TOKEN` | ja | Bot-Token der Sandbox-App (`xoxb-…`) |
| `SANDBOX_SLACK_CHANNEL_ID` | ja | Testkanal |
| `SANDBOX_SLACK_TEST_USER_ID` | ja | DM-Ziel im Sandbox-Workspace |
| `TEST_DS_B_ID`, `TEST_TEMPLATE_ID` | ja | Notion-Testkopie |
| `TEST_PUTZPLAN_RELATION_PROP` | nein | Default `Putztest` |

## Stand der Testläufe (30.07.2026)

**Funktioniert** — Dry Run gegen Sandbox-Slack + Notion-Testkopie läuft komplett durch:
28 Wochenseiten geladen, Sammelseiten korrekt ignoriert, 204 Mitglieder über mehrere
Seiten paginiert, davon 70 losbar, Zyklus 9 (KW 33–36) geplant, je 2 neue + 2 alte
Mitglieder gezogen, DMs umgeleitet. Poll-Modus läuft ebenfalls sauber.

**Noch offen:**

| Problem | Symptom | Behebung |
|---|---|---|
| Sandbox-App hat zu wenige Scopes | `missing_scope`, vorhanden nur `channels:history,chat:write` | App mit [slack-app-manifest.yml](slack-app-manifest.yml) neu konfigurieren und **neu installieren**. Fehlen: `im:write`, `im:history`, `users:read`, `users:read.email`, `reactions:read`. Ohne die gehen keine DMs und keine Reaktionsabfrage. |
| Bot ist nicht im Sandbox-Kanal | `not_in_channel` | Im Testkanal `/invite @putzbot` ausführen. |
| Datenfehler in der Mitgliederliste | Mitglied „Zadlo, " hat keinen Vornamen | In Notion den Vornamen ergänzen. Sonst greift zwar der Fallback (Anzeige „Zadlo"), aber die abgeleitete E-Mail `.zadlo@das-habitat.de` ist unbrauchbar — diese Person bekäme produktiv nie eine DM. |

## Stand der Testläufe (01.08.2026) — End-to-End bestanden

Der komplette Reschedule-Durchlauf ist über `sandbox_test.yml` gegen Sandbox-Slack und
die Notion-Testkopie gelaufen:

| Schritt | Ergebnis |
|---|---|
| `plan` scharf | KW 33–36 angelegt, je 4 Mitglieder, 2 neu + 2 alt, 16 DMs raus |
| **Metadata-Rückweg** | **30 von 30 Nachrichten mit Metadata** — die Kernannahme hält |
| ❌ auf eine Auslos-DM | erkannt, Nachfrage verschickt |
| Zuordnung pro Mitglied | 16 Mitglieder lasen denselben Verlauf, nur der Betroffene reagierte |
| Antwort „35" (volle Woche) | abgelehnt mit Notion-Link, nichts umgetragen |
| Antwort „40" (freie Woche) | umgetragen, KW-40-Seite angelegt, KW 36 nachgelost, Bestätigung raus |
| zweiter Poll | „Nichts Neues." — keine Doppelverarbeitung |
| `draw` scharf | KW 31 von 2 auf 4 aufgefüllt, **eine** Kanalnachricht, **keine** DMs |

Damit ist die eine Annahme bestätigt, auf der der ganze Reschedule-Flow steht: Slack
liefert die Message-Metadata über `conversations_history` zurück. `read_dm_history` gibt
das bei `DEBUG=true` mit aus — bei künftigen Läufen ein Blick auf diese Zeile genügt.

Zwei Dinge, die dabei aufgefallen und behoben sind: die DM-Zuordnung pro Mitglied (ohne
sie hätte ein einzelnes ❌ im Sandbox die ganze Wochencrew verschoben) und die
Fehlermeldung bei einer vollen Zielwoche, die vorher behauptete, sie hätte die Eingabe
nicht verstanden.

## Was ich von dir brauche, um mitzutesten

- [x] `Jahr`-Property in der Putzplan-DB (alle 28 Seiten auf 2026).
- [x] Kopie der Putzplan-DB: „❌ Putzplan (NUR FÜR TESTS)", Data-Source-ID `565b71ac-7d09-82ec-8ce8-870a78528167`. Inhalte inkl. Relationen sind mitgekommen, die Historie steht also für Tests zur Verfügung.
- [x] Zweite Relation auf der Mitgliederliste heißt **`Putztest`** → `PUTZPLAN_RELATION_PROP=Putztest`.
- [x] Sandbox-Slack-App eingerichtet.
- [x] `TEST_TEMPLATE_ID` geprüft: die Testkopie führt „Neue Putzcrew (Automation)" unter
      `0a5b71ac-7d09-83ee-8af0-01b245383ca7`, passend zu `TEMPLATE_ID` produktiv.
- [x] Sandbox-Kanal-ID und Sandbox-User-ID hinterlegt.
- [x] `SANDBOX_SLACK_TOKEN` und `SANDBOX_SLACK_CHANNEL_ID` in den GitHub-Secrets.
      Kamen anfangs leer an, obwohl sie in der Übersicht standen — GitHub lässt ein
      Secret mit leerem Wert zu, und das sieht dort aus wie jedes andere. Neu anlegen
      (nicht bearbeiten) hat es behoben.
- [ ] Die Tokens **nicht** in den Chat — die gehören in die `.env` bzw. in die GitHub-Secrets.
