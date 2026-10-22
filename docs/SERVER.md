# Rechnungs-Tinder auf dem eigenen Server betreiben

Rechnungs-Tinder läuft als **Dienst auf eurem Server** im Hintergrund und startet nach einem
Neustart automatisch wieder. Alle Mitarbeiter öffnen es im Browser (PC, Tablet, Smartphone)
unter `http://<server>:8765` und melden sich mit der PIN an. Python oder sonstige Software
muss auf den Arbeitsplätzen nicht installiert werden.

Es gibt drei Wege. Welcher passt, hängt vom Server ab:

| Server | Weg |
|---|---|
| **Ubuntu-Server, Rechnungen auf einer Synology** (auch ältere DSM-Versionen ohne Docker) | **A – Installationsskript** (empfohlen) |
| Synology/QNAP-NAS mit „Container Manager“ / „Container Station“ (ohne extra Server) | **B – direkt auf dem NAS** |
| Windows-Server ohne Docker | **C – RechnungsTinder.exe** |

Bei Weg A läuft das Programm auf dem Ubuntu-Server. Die Synology stellt nur den Ordner per
Windows-Dateifreigabe (SMB) bereit – auf dem NAS muss dafür **kein Docker** laufen.

```
 PC / Tablet / Smartphone ──Browser──▶ Ubuntu-Server (Rechnungs-Tinder) ──SMB──▶ Synology (Ordner „Rechnungen“)
```

---

## Synology vorbereiten

Die Menüs heißen je nach DSM-Version etwas anders; beide Varianten sind angegeben.

**1. SMB-Dienst einschalten**
- DSM 6/7: *Systemsteuerung → Dateidienste → SMB* → „SMB-Dienst aktivieren“.
- DSM 5: *Systemsteuerung → Win/Mac/NFS → Windows-Dateidienst aktivieren*.
- Unter *Erweiterte Einstellungen*: **Maximales SMB-Protokoll = SMB3**, **Minimales = SMB2**
  (falls vorhanden). Das Installationsskript findet die passende Version selbst; nur wenn das NAS
  gar kein SMB2/3 kann, wird das alte, unsichere SMB1 benutzt (dann bitte DSM aktualisieren).

**2. Gemeinsamen Ordner anlegen** (falls noch nicht vorhanden)
- *Systemsteuerung → Gemeinsamer Ordner → Erstellen*, Name z. B. `Rechnungen`.
- Unterordner (z. B. `2026-10`, `Firma X`) sind später in der App auswählbar.

**3. Eigenen Benutzer für das Programm anlegen**
- *Systemsteuerung → Benutzer* (DSM 7: *Benutzer und Gruppe*) *→ Erstellen*, z. B. `rechnungen`
  mit sicherem Passwort.
- Bei den Berechtigungen für den Ordner `Rechnungen`: **Lesen/Schreiben** ankreuzen
  (für Notizen und das Verschieben nach *Bewilligt*/*Abgelehnt*). Andere Ordner: *Kein Zugriff*.
- Bei den Anwendungen genügt **SMB** (bzw. „Windows-Dateidienst“).

**4. Notieren:** IP-Adresse der Synology (*Systemsteuerung → Netzwerk → Netzwerkschnittstelle*,
z. B. `192.168.1.10`), Ordnername, Benutzer, Passwort. Am besten der Synology im Router eine feste
IP-Adresse geben.

---

## A – Ubuntu-Server mit Installationsskript (empfohlen)

Voraussetzung: Ubuntu 20.04 oder neuer, Internetzugang während der Installation, ein Benutzer mit
`sudo`-Rechten.

**1. Programm auf den Server holen**, z. B.:

```sh
git clone https://github.com/Bugra-San/Invoice-Tinder.git
cd Invoice-Tinder
```

(Ist das Repository privat, fragt `git` nach GitHub-Benutzer und einem Zugangs-Token. Alternativ
auf GitHub *Code → Download ZIP*, auf den Server kopieren, mit `unzip` entpacken und das Skript mit
`sudo bash installieren-ubuntu.sh` starten.)

**2. Installationsskript starten:**

```sh
sudo ./installieren-ubuntu.sh
```

Das Skript fragt nach IP-Adresse der Synology, Ordnername, Benutzer, Passwort, Port und PIN
und erledigt dann alles Weitere:

- installiert Docker und die SMB-Werkzeuge,
- bindet die Synology-Freigabe dauerhaft unter `/mnt/rechnungen` ein und **sucht dabei die
  passende SMB-Version** (wichtig bei älteren Geräten),
- **prüft Lesen und Schreiben** auf dem NAS und sagt bei Problemen konkret, woran es liegt
  (falsches Passwort, Ordner nicht gefunden, NAS nicht erreichbar, fehlende Schreibrechte),
- installiert das Programm nach `/opt/rechnungs-tinder` und startet es,
- richtet den Autostart ein: Nach einem Neustart wird erst das NAS eingebunden, dann das Programm
  gestartet,
- öffnet bei aktiver Firewall (`ufw`) den Port.

Am Ende zeigt es die Adresse (z. B. `http://192.168.1.20:8765`) und die PIN an. Fertig.

**Aktualisieren:** neue Version holen (`git pull` bzw. neue ZIP) und `sudo ./installieren-ubuntu.sh`
erneut starten → „Einstellungen übernehmen?“ mit *J* bestätigen.

**Einstellungen ändern** (andere PIN, neues NAS-Passwort, anderer Ordner): Skript erneut starten
und die Frage nach dem Übernehmen mit *n* beantworten.

**Entfernen:** `sudo ./installieren-ubuntu.sh --entfernen` (die Rechnungen auf dem NAS bleiben
unangetastet).

**Ohne NAS ausprobieren:** `sudo ./installieren-ubuntu.sh --lokaler-ordner /srv/rechnungen`
verwendet einen Ordner auf dem Server selbst.

Wo liegt was?

| | |
|---|---|
| Programm | `/opt/rechnungs-tinder` |
| NAS-Zugangsdaten (nur für root lesbar) | `/etc/rechnungs-tinder/nas-zugang` |
| Antworten der Einrichtung (ohne Passwort) | `/etc/rechnungs-tinder/einrichtung.conf` |
| Einbindung des NAS | Zeile mit `# rechnungs-tinder` in `/etc/fstab`, Ordner `/mnt/rechnungen` |
| PIN, Anmeldeschlüssel, „zuletzt verwendet“ | Docker-Volume `rechnungs-tinder_daten` |

### A2 – Ohne Skript, von Hand (für Fachleute)

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo apt install -y cifs-utils
cp .env.beispiel .env && nano .env      # PIN, NAS_ADRESSE, NAS_FREIGABE, NAS_BENUTZER, NAS_PASSWORT
sudo docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d --build
```

Hier bindet Docker die Freigabe beim Start des Containers selbst ein. Ist das NAS beim Hochfahren
des Servers noch nicht erreichbar, startet der Container nicht – deshalb ist das Skript
(Einbindung über `/etc/fstab` mit Autostart-Reihenfolge) die robustere Wahl.

**Nützliche Befehle** (im Ordner `/opt/rechnungs-tinder`, bzw. überall mit
`--project-directory /opt/rechnungs-tinder`):

| | |
|---|---|
| Läuft es? | `sudo docker compose ps` (Status *healthy*) |
| Protokoll ansehen | `sudo docker compose logs -f` |
| Neu starten | `sudo docker compose restart` |
| Stoppen | `sudo docker compose down` |
| NAS eingebunden? | `findmnt /mnt/rechnungen` |
| Aktualisieren | Installationsskript erneut ausführen (siehe oben) |

**Fertiges Image statt selbst bauen:** Bei jedem Push baut GitHub automatisch ein Image
(`ghcr.io/bugra-san/invoice-tinder`, für normale Server und ARM-NAS). Dafür in
`docker-compose.yml` die Zeile `build: .` entfernen und bei `image:` z. B.
`ghcr.io/bugra-san/invoice-tinder:latest` eintragen. Ist das Repository privat, vorher einmal
`docker login ghcr.io` (GitHub-Benutzer + Token mit Recht `read:packages`).

---

## B – Direkt auf einer Synology (Container Manager)

1. Im Paket-Zentrum **Container Manager** installieren.
2. In der File Station einen Ordner `docker/rechnungs-tinder` anlegen und den Inhalt dieses
   Repositorys hineinkopieren.
3. Die Benutzer-ID ermitteln: Systemsteuerung → Terminal & SNMP → SSH aktivieren, per SSH
   anmelden und `id rechnungen` eingeben (z. B. `uid=1027 gid=100`).
4. `.env.beispiel` als `.env` speichern und eintragen:
   ```
   PIN=482913
   RECHNUNGEN_ORDNER=/volume1/Rechnungen
   PUID=1027
   PGID=100
   ```
5. Container Manager → **Projekt** → *Erstellen* → Pfad `docker/rechnungs-tinder` wählen →
   „vorhandene docker-compose.yml verwenden“ → *Weiter* → *Fertig*.
6. Aufruf: `http://<IP-der-Synology>:8765`

Die Rechnungen bleiben auf dem NAS; eine Netzwerkfreigabe ist hier nicht nötig.
(QNAP: in der *Container Station* unter *Anwendungen* ebenso mit der `docker-compose.yml`.)

---

## C – Windows-Server ohne Docker

1. **RechnungsTinder.exe** herunterladen: GitHub → *Actions* → „Testen und bauen“ → neuester
   Lauf → *Artifacts* → `RechnungsTinder-Windows` (bei Versionen auch unter *Releases*).
   Die Datei z. B. nach `C:\RechnungsTinder\` kopieren.
2. Probelauf in der Eingabeaufforderung:
   ```bat
   C:\RechnungsTinder\RechnungsTinder.exe --server --ordner "\\192.168.1.10\Rechnungen" --pin 482913
   ```
3. Firewall öffnen (Eingabeaufforderung als Administrator):
   ```bat
   netsh advfirewall firewall add rule name="Rechnungs-Tinder" dir=in action=allow protocol=TCP localport=8765
   ```
4. **Automatisch starten:** *Aufgabenplanung* → *Einfache Aufgabe erstellen* →
   Trigger „Beim Start des Computers“ → Programm `C:\RechnungsTinder\RechnungsTinder.exe`,
   Argumente `--server --ordner "\\192.168.1.10\Rechnungen" --pin 482913`.
   In den Eigenschaften der Aufgabe: „Unabhängig von der Benutzeranmeldung ausführen“ und als
   Benutzer ein Konto wählen, das **Zugriff auf die NAS-Freigabe** hat (nicht „SYSTEM“ – das darf
   nicht auf Netzwerkfreigaben zugreifen). Unter *Einstellungen* „Aufgabe beenden, falls länger
   als …“ abschalten.

Die Einstellungen (PIN, zuletzt verwendete Ordner) liegen in
`C:\Users\<Konto>\.rechnungs-tinder-einstellungen.json`.

---

## Einstellungen im Überblick

| `.env` (Docker) | Programm-Option / Umgebungsvariable | Bedeutung |
|---|---|---|
| `PIN` | `--pin` / `RT_PIN` | PIN zum Anmelden. Ändern meldet alle Geräte ab. |
| `PORT` | `--port` / `RT_PORT` | Port (Standard 8765) |
| `RECHNUNGEN_ORDNER` | `--ordner` / `RT_ORDNER` | Rechnungsordner; mehrere mit `;` trennen |
| `ORDNER_BEWILLIGT`, `ORDNER_ABGELEHNT` | `RT_BEWILLIGT`, `RT_ABGELEHNT` | Namen der Zielordner (Standard *Bewilligt*/*Abgelehnt*) |
| `PUID`, `PGID` | – | Benutzer, unter dem Dateien geändert werden |
| `HINTER_PROXY` | `--hinter-proxy` / `RT_PROXY` | `1`, wenn ein Reverse-Proxy (HTTPS) davor sitzt |
| – | `--einstellungen` / `RT_EINSTELLUNGEN` | Ort der Einstellungsdatei |

**Was wird wo gespeichert?**
- Die PDFs (inkl. Notizen) und die Zielordner *Bewilligt*/*Abgelehnt* liegen im Rechnungsordner
  auf dem NAS. Der Bearbeitungsstand steht dort in der versteckten Datei `.rechnungs-tinder.json`.
- PIN, Anmeldeschlüssel und „zuletzt verwendet“ liegen im Docker-Volume `daten`
  bzw. in der Einstellungsdatei. Geht diese verloren, müssen sich nur alle neu anmelden.

## Sicherheit

- Nur im **internen Netz** betreiben. Für Zugriff von unterwegs ein **VPN** verwenden
  (z. B. das VPN des Routers/NAS) – den Port nicht ins Internet freigeben.
- Eine PIN mit mindestens 6 Ziffern wählen. Nach 5 Fehlversuchen wird ein Gerät 5 Minuten gesperrt.
- **HTTPS** (empfohlen, Pflicht für eine spätere iOS-App außerhalb des Heimnetzes): einen
  Reverse-Proxy davorsetzen, z. B. Synology *Systemsteuerung → Anmeldeportal → Erweitert →
  Reverse Proxy* oder Caddy/nginx, und `HINTER_PROXY=1` setzen.

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| Seite lädt nicht | Läuft der Container (`docker compose ps`)? Firewall/Port 8765 offen? |
| In der App sind keine Rechnungen/Ordner zu sehen | Ist das NAS eingebunden? `findmnt /mnt/rechnungen` – wenn nicht: `sudo mount /mnt/rechnungen` (zeigt die Fehlermeldung) und danach `sudo docker compose --project-directory /opt/rechnungs-tinder restart`. |
| Skript meldet „Benutzer oder Passwort falsch“ | Benutzer/Passwort auf der Synology prüfen, Berechtigung für den Ordner (Lesen/Schreiben) und für die Anwendung SMB setzen. |
| Skript meldet „NAS nicht erreichbar“ | IP-Adresse prüfen (`ping 192.168.1.10`), SMB-Dienst auf der Synology aktiviert? Firewall der Synology erlaubt SMB? |
| Skript meldet „fehlende SMB-Unterstützung im Kernel“ | `sudo apt install linux-modules-extra-$(uname -r)` und Skript erneut starten. |
| Im Protokoll „Ordner … nicht erreichbar“ (Weg A2) | NAS-Adresse/Freigabe/Benutzer/Passwort in der `.env` prüfen; `cifs-utils` installiert? Bei älteren NAS `SMB_VERSION=2.1` versuchen. |
| „Keine Berechtigung“ beim Verschieben oder bei Notizen | Der NAS-Benutzer braucht Schreibrechte; `PUID`/`PGID` passend setzen. |
| Rechnung ist „in einem anderen Programm geöffnet“ | Die PDF am PC schließen und erneut versuchen. |
| PIN vergessen | `sudo cat /etc/rechnungs-tinder/einrichtung.conf` (Weg A), in der `.env` (A2/B) bzw. in den Argumenten der geplanten Aufgabe (Windows). |
