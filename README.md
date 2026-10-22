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
| Rechnung ansehen | Auf die Rechnung tippen oder **🔍 Ansehen** |
| Zoomen | Knöpfe **＋ Größer** / **－ Kleiner**, mit zwei Fingern, doppelt tippen (Smartphone/Tablet) oder Strg + Mausrad |
| Notiz schreiben | **✎ Notiz** → auf die Stelle in der Rechnung tippen → Text eingeben → **Notiz speichern** |
| Zeichnen / Anstreichen | **🖊 Zeichnen** → mit Maus oder Finger malen |
| Notiz entfernen | **↶ Löschen** entfernt die zuletzt gemachte Notiz oder Zeichnung |
| Entscheidung zurücknehmen | **↶ Zurück** holt die zuletzt entschiedene Rechnung wieder zurück |

Notizen und Zeichnungen werden **direkt in die PDF-Datei geschrieben** (als normale
PDF-Anmerkungen). Man sieht sie also auch später in jedem PDF-Programm (Adobe Reader, Browser …).

Der Fortschritt wird im Ordner in der versteckten Datei `.rechnungs-tinder.json` gespeichert.
Wird das Programm zwischendurch geschlossen, geht es beim nächsten Mal an derselben Stelle weiter.
Gibt es im Zielordner schon eine Datei mit gleichem Namen, wird nichts überschrieben, sondern
z. B. `Rechnung (2).pdf` angelegt.

## Auf dem Server betreiben (empfohlen für Firmen)

Rechnungs-Tinder läuft als Dienst auf dem eigenen Server – als **Docker-Container** (Linux-Server,
Synology/QNAP-NAS) oder als **RechnungsTinder.exe** (Windows-Server, ohne Python). Die
Rechnungen kommen direkt aus einem NAS-Ordner; alle Mitarbeiter öffnen das Programm im Browser
unter `http://<server>:8765` und melden sich mit der PIN an.

Ubuntu-Server mit Rechnungen auf einer Synology (auch ältere Modelle ohne Docker):

```sh
git clone https://github.com/Bugra-San/Invoice-Tinder.git && cd Invoice-Tinder
sudo ./installieren-ubuntu.sh    # fragt NAS-Zugang und PIN ab, richtet alles ein
```

Schritt-für-Schritt-Anleitung für alle Varianten: **[docs/SERVER.md](docs/SERVER.md)**

## Installation und Start auf einem einzelnen PC

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

## Auf dem Smartphone oder Tablet benutzen

Das Programm läuft weiter auf dem Computer/Server, auf dem die Rechnungen liegen. Smartphones und
Tablets im **gleichen WLAN** greifen über den Browser darauf zu – eine App muss dafür nicht
installiert werden.

1. Auf dem Computer einmalig mit dem freizugebenden Ordner starten:
   - Windows: `start-netzwerk.bat --ordner "D:\Rechnungen"` (danach reicht ein Doppelklick auf `start-netzwerk.bat`)
   - macOS/Linux: `./start-netzwerk.sh --ordner ~/Rechnungen`

   Windows fragt beim ersten Mal, ob das Programm ins Netzwerk darf → **Zugriff zulassen**
   (privates Netzwerk).
2. Das Programm-Fenster zeigt die **Adresse** (z. B. `http://192.168.1.20:8765/`) und die **PIN**.
3. Auf dem Smartphone diese Adresse im Browser öffnen und die PIN eingeben. Die Anmeldung bleibt
   gespeichert.
4. Tipp: Über **Teilen → Zum Home-Bildschirm** (iPhone) bzw. **Zum Startbildschirm hinzufügen**
   (Android) bekommt man ein eigenes Symbol „Rechnungen“, das sich wie eine App im Vollbild öffnet.

Vom Smartphone aus sind **nur die freigegebenen Ordner** (und deren Unterordner) erreichbar.
Das Ordner-Fenster von Windows gibt es dort nicht; stattdessen wählt man den Ordner in einer
großen Liste. Mehrere Geräte können gleichzeitig arbeiten, der Stand liegt auf dem Server.

Die Darstellung passt sich an kleine Bildschirme an: alle Knöpfe unten in Daumenreichweite,
Symbol mit Beschriftung darunter, Rechnung in voller Bildschirmbreite, eine eigene Anordnung für
das Querformat und ein Notizfeld, das von der Bildschirmtastatur nicht verdeckt wird. Die Seiten
werden passend zur Auflösung des Geräts (auch für Retina-Displays) gestochen scharf berechnet.

Weitere Optionen: `--pin 123456` (eigene PIN festlegen; alte Anmeldungen werden ungültig),
`--port 8765`, `--zertifikat cert.pem --schluessel key.pem` (HTTPS).
**Bitte den Server nicht ungeschützt ins Internet stellen** – für Zugriff von unterwegs ein VPN
verwenden.

### Eigene iOS-App (geplant)

Alle Funktionen stehen über eine dokumentierte Schnittstelle zur Verfügung
(**[docs/API.md](docs/API.md)**): Anmeldung mit PIN, Ordner durchsuchen, Seiten als Bilder in
beliebiger Auflösung, Original-PDF, Entscheiden, Notizen/Zeichnungen und Verschieben. Eine
spätere iOS-App (z. B. SwiftUI) spricht genau diese Schnittstelle an und greift so auf den Ordner
am Server zu – am Server muss dafür nichts geändert werden.

## Einstellungen

Die Datei `.rechnungs-tinder-einstellungen.json` im persönlichen Ordner des Benutzers
(z. B. `C:\Users\Name\`) wird beim ersten Öffnen eines Ordners angelegt. Dort lassen sich die
Zielordner ändern – relativ zum Rechnungsordner oder als vollständiger Pfad:

```json
{
  "bewilligt_ordner": "Bewilligt",
  "abgelehnt_ordner": "D:\\Buchhaltung\\Abgelehnt",
  "freigaben": ["D:\\Rechnungen"],
  "pin": "482913"
}
```

`freigaben` und `pin` gelten für den Netzwerk-Modus (werden beim ersten Start automatisch
eingetragen bzw. erzeugt).

## Technik

- Python-Programm (Flask, im Serverbetrieb mit dem Webserver *waitress*), ausgeliefert als
  Docker-Image (`Dockerfile`, `docker-compose.yml`) oder als einzelne Windows-Datei
  (`packaging/RechnungsTinder.spec`, wird von GitHub Actions automatisch gebaut). Standardmäßig nur auf dem eigenen Rechner erreichbar (`127.0.0.1`),
  im Netzwerk-Modus mit PIN-Anmeldung, signierten Zugangs-Tokens, Sperre nach mehreren falschen
  PIN-Eingaben und Beschränkung auf die freigegebenen Ordner.
- Schnittstelle für Browser und Apps: `/api/v1` ([docs/API.md](docs/API.md)).
- PDF-Anzeige und -Anmerkungen mit [PyMuPDF](https://pymupdf.readthedocs.io/)
  (Lizenz: AGPL bzw. kommerziell von Artifex – für den internen Einsatz unproblematisch,
  bei Weitergabe/Verkauf des Programms bitte die Lizenzbedingungen prüfen).
- Oberfläche: ein einfaches HTML/CSS/JavaScript ohne weitere Abhängigkeiten
  (`rechnungs_tinder/static/`), funktioniert mit Maus und Touchscreen, als Web-App auf dem
  Home-Bildschirm installierbar.

Tests:

```sh
pip install pytest
python -m pytest
```
