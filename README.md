# Rechnungs-Tinder

Rechnungen (PDF) aus einem Ordner nacheinander anzeigen und mit einer Wischbewegung entscheiden:

- **nach rechts wischen** → bewilligt
- **nach links wischen** → abgelehnt

Statt zu wischen kann man auch auf die großen Knöpfe **✗ Ablehnen** / **✓ Bewilligen** tippen
(oder die Pfeiltasten ← / → drücken). Wenn alle Rechnungen geprüft sind, werden sie mit einem
Klick in die Unterordner **Bewilligt** und **Abgelehnt** verschoben.

Die Oberfläche ist bewusst einfach gehalten: große Schrift, große Knöpfe mit Text, starke Farben
und immer nur wenige Möglichkeiten auf einmal.

## Funktionen

| Funktion | So geht's |
| --- | --- |
| Ordner auswählen | **📂 Ordner auswählen** – öffnet das normale Ordner-Fenster von Windows. Zuletzt verwendete Ordner stehen als Knöpfe darunter. |
| Rechnung ansehen | Auf die Rechnung tippen oder **🔍 Ansehen & Notiz** |
| Zoomen | Knöpfe **＋** / **－**, mit zwei Fingern auf dem Tablet, oder Strg + Mausrad |
| Notiz schreiben | **✎ Notiz** → auf die Stelle in der Rechnung tippen → Text eingeben → **Notiz speichern** |
| Zeichnen / Anstreichen | **🖊 Zeichnen** → mit Maus oder Finger malen |
| Notiz entfernen | **↶ Notiz löschen** entfernt die zuletzt gemachte Notiz oder Zeichnung |
| Entscheidung zurücknehmen | **↶ Zurück** holt die zuletzt entschiedene Rechnung wieder zurück |

Notizen und Zeichnungen werden **direkt in die PDF-Datei geschrieben** (als normale
PDF-Anmerkungen). Man sieht sie also auch später in jedem PDF-Programm (Adobe Reader, Browser …).

Der Fortschritt wird im Ordner in der versteckten Datei `.rechnungs-tinder.json` gespeichert.
Wird das Programm zwischendurch geschlossen, geht es beim nächsten Mal an derselben Stelle weiter.
Gibt es im Zielordner schon eine Datei mit gleichem Namen, wird nichts überschrieben, sondern
z. B. `Rechnung (2).pdf` angelegt.

## Installation und Start

Voraussetzung: [Python 3.10 oder neuer](https://www.python.org/downloads/)
(unter Windows bei der Installation „Add Python to PATH“ anhaken).

- **Windows:** Doppelklick auf `start.bat`
- **macOS:** Doppelklick auf `start.command`
- **Linux:** `./start.sh`

Beim ersten Start wird alles Nötige automatisch eingerichtet. Danach öffnet sich das Programm im
Browser. Das schwarze Fenster muss geöffnet bleiben, solange man mit dem Programm arbeitet; zum
Beenden einfach schließen.

Manuell:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip ...
.venv/bin/python -m rechnungs_tinder             # Optionen: --port 8765 --kein-browser
```

## Einstellungen

Die Datei `.rechnungs-tinder-einstellungen.json` im persönlichen Ordner des Benutzers
(z. B. `C:\Users\Name\`) wird beim ersten Öffnen eines Ordners angelegt. Dort lassen sich die
Zielordner ändern – relativ zum Rechnungsordner oder als vollständiger Pfad:

```json
{
  "bewilligt_ordner": "Bewilligt",
  "abgelehnt_ordner": "D:\\Buchhaltung\\Abgelehnt"
}
```

## Technik

- Python-Programm (Flask), das nur auf dem eigenen Rechner erreichbar ist (`127.0.0.1`);
  jeder Zugriff braucht einen zufälligen Schlüssel, der bei jedem Start neu erzeugt wird.
- PDF-Anzeige und -Anmerkungen mit [PyMuPDF](https://pymupdf.readthedocs.io/)
  (Lizenz: AGPL bzw. kommerziell von Artifex – für den internen Einsatz unproblematisch,
  bei Weitergabe/Verkauf des Programms bitte die Lizenzbedingungen prüfen).
- Oberfläche: ein einfaches HTML/CSS/JavaScript ohne weitere Abhängigkeiten
  (`rechnungs_tinder/static/`), funktioniert mit Maus und Touchscreen.

Tests:

```sh
pip install pytest
python -m pytest
```
