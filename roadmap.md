## Neuer Ablauf Schematisch:

Das Jahr ist in 13 Zyklen (je 4 Wochen) unterteilt. In der letzten Woche des aktuellen Zyklus wird für den nächsten Zyklus ausgelost, also z.B. in der letzten Woche von Zyklus 1 (KW 4) für Zyklus 2 (KW 5-8). Das ist der Puffer, damit die Mitglieder den Termin einplanen können). 
Die Mitglieder werden benachrichtigt, wenn sie ausgelost wurden und können sich entscheiden, zu einem anderen (konkreten) Zeitpunkt zu putzen, dann wird neu ausgelost. 
Jede Woche wird die jeweilige Putzcrew benachrichtigt

## Prozesse/Funktionen

## Gesamtzyklus
### Plan
- Auslöser: Zeit (alle 4 Wochen, jeweils zu Beginn der letzten Woche des aktuellen Zyklus)
- Eine Schleife durch die 4 Wochen des nächsten Zyklus:
	- Bot überprüft, ob die Seite auf Notion erstellt ist,
		- Wenn nicht, erstellt er die Seite
	- Bot überprüft, wie viele eingetragen sind,
		- Wenn nicht genug eingetragen sind, wird für die jeweilige Woche der `Raffle` Prozess ausgelöst.
- Nachdem das für alle Wochen des nächsten Zyklus wiederholt wurde, endet dieser Prozess.

### Raffle
- Auslöser: Manuell durch andere Prozesse
- Benötigt KW
- Löst `Notion Lookup` mit der KW aus, speichert das Output als `page_properties`
- Löst `Get Members` aus, speichert das Output als `member_list`
- Löst `Build Candidate Pool` mit `member_list` und `page_properties` aus, speichert das Output als `candidate_pools`
- Sampled `needed` Mitglieder aus `candidate_pools`:
	- Variablen für die Anzahl an alten und neuen Mitgliedern, je für Kandidaten und Putzende
	- Da, wo weniger von Putzen wird jemand ausgelost, wenn es noch mindestens 3 Kandidaten gibt
		- Sonst wird von allen Kandidaten jemand ausgelost 
	- Wenn es gleich viele gibt, wird von allen Kandidaten jemand ausgelost
	- %% evtl könnte ich noch die worst case Wahrscheinlichkeiten berechnen %%
- Löst `Update Notion Page` aus, um die neu ausgelosten Mitglieder einzutragen
- Alle die dazu neu ausgelost wurden, werden von dem Bot per PM benachrichtigt.
	- evtl könnten auch einfach alle für den nächsten Zyklus benachrichtigt werden, also auch die, die schon vorher eingetragen wurden. Dadurch könnten Mitglieder dann aber endlos verlängern ohne dranzukommen.
- Der Bot fordert in der PM dazu auf, mit `Häkchen` zu bestätigen oder `Kreuz` zu verschieben.
	- %% es ist bisschen unklar, wie ich das registrieren kann %%
1. Wenn das Mitglied mit `Häkchen` bestätigt ist der Prozess für dieses Mitglied beendet
2. Wenn das Mitglied mit `Kreuz` absagt, wird `Reschedule` ausgelöst

### Reschedule
- Auslöser: Das Mitglied reagiert mit Kreuz auf die Auslosnachricht des Bots
- Benötigt: Member ID, KW_alt %% Kann man die KW irgendwie ableiten/nachschauen? %%
- Der Bot fragt das Mitglied per PM nach der Woche, in der es putzen möchte 
	- %% evtl geht das noch sauberer über Reaktionen/Buttons; sonst soll das Mitglied einfach die Wochennummer als Zahl reinschreiben, also z.B. `22` %%
- Wenn eine valide Woche (liegt in den nächsten 10 Zyklen) angegeben wurde:
	- wird `Notion Lookup` für die alte und die Neue Woche ausgelöst und die Outputs als `page_properties_old` bzw. `page_properties_new`gespeichert
	- wird das Mitglied aus der alten Woche ausgetragen 
	- wird das Mitglied in die neue Woche eingetragen 
- Wenn in der alten Woche weniger als 4 Mitglieder eingetragen sind:
	- wird für diese alte Woche der `Raffle` Prozess ausgelöst.


### Remind
- Auslöser: Zeit (wöchentlich am Montag) %% evtl erst an einem anderen Tag %%
- Bot holt sich die Daten der aktuellen Woche per `Notion Lookup` und erstellt damit die Nachricht.
	- Die Nachricht ist ein Standardtext und inkludiert die Erwähnung (mit @) der Mitglieder die diese Woche drinstehen
- Diese Nachricht schickt er dann auf Slack in den Kanal `#räumen-und-ratschen`

### Notion Lookup
- Auslöser: Manuell durch andere Prozesse
- Benötigt: KW
- Verwendet die Notion Verbindung, um alle Properties der Woche nachzuschauen und einem Dictionary zu speichern (mit einer zusätzlichen Page status property für error handling) 
- Return: Dictionary 

### Get Members
- Auslöser: Manuell durch andere Prozesse
- Lädt die Mitgliederliste aus Notion
	- %% hier schon ein erster Filter: 
		- Nur echte Mitglieder
			- Kein Emoji
			- Richtige Properties
		- Nicht die, die sich per `Putzstatus` Property ausgetragen haben %%
- Iteration durch die Mitgliederliste:
	- Name parsen → `Full Name`
	- Email parsen → `Email`
	- Mitglied in einer List of Dictionaries speichern mit  `ID`, `Full Name`, `Email`, `Eintrittsdatum`, `Putzstatus` und `Putzplan` 
- Return: List of Dictionaries

### Build Candidate Pool
- Auslöser: Manuell durch andere Prozesse
- Benötigt: List of Dictionaries mit den Mitgliedern, Dictionary für die Notion Seite
- %% evtl die Formatierung der Inputvariablen überprüfen %%
- Variablen Definieren:
	- Neue List of Dictionaries: `candidate_pool_all`
	- Neue List of Dictionaries: `candidate_pool_new`
	- Neue List of Dictionaries: `candidate_pool_old`
	- Neuer Int: min_size = 5+`needed`
- Iteration durch die Mitgliederliste:
	- Wenn der Putzstatus passt:
	- Wenn das Mitglied in der Woche nicht schon putzt:
	- Wenn len(Putzrelation) < globaler Putzcounter:
	- ED wird gecheckt und das Mitglied zu den entsprechenden Listen hinzugefügt
- Wenn zu wenige Leute zur Auswahl stehen:
	- wird der globale Putzcounter um eins erhöht und `Build Candidate Pool` erneut ausgelöst 
	- %% rekursiv wäre cool, checke ich aber noch nicht, also maybe einfach den loop copy pasten %%
- Output: Dictionary mit drei LoDs
