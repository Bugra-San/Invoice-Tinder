# Rechnungs-Tinder auf dem eigenen Server betreiben

Rechnungs-Tinder läuft als **Dienst auf eurem Server** im Hintergrund und startet nach einem
Neustart automatisch wieder. Alle Mitarbeiter öffnen es im Browser (PC, Tablet, Smartphone)
unter `http://<server>:8765` und melden sich mit der PIN an. Python oder sonstige Software
muss auf den Arbeitsplätzen nicht installiert werden.

Es gibt drei Wege. Welcher passt, hängt vom Server ab:

| Server | Weg |
|---|---|
| Linux-Server (Ubuntu, Debian, …) oder Windows-Server mit Docker | **A – Docker** (empfohlen) |
| Synology- oder QNAP-NAS mit „Container Manager“ / „Container Station“ | **B – direkt auf dem NAS** |
| Windows-Server ohne Docker | **C – RechnungsTinder.exe** |

---

## Vorbereitung auf dem NAS (für alle Wege)

1. Freigegebenen Ordner für die Rechnungen anlegen, z. B. `Rechnungen`.
   Unterordner (z. B. `2026-10`, `Firma X`) sind später in der App auswählbar.
2. Einen eigenen NAS-Benutzer anlegen, z. B. `rechnungen`, mit **Lesen und Schreiben** auf diese
   Freigabe (Schreiben ist nötig für Notizen und das Verschieben nach *Bewilligt*/*Abgelehnt*).
3. Notieren: IP-Adresse des NAS (z. B. `192.168.1.10`), Name der Freigabe, Benutzer, Passwort.

---

## A – Docker auf einem Linux-Server (empfohlen)

**1. Docker installieren** (einmalig, Ubuntu/Debian):

```sh
curl -fsSL https://get.docker.com | sudo sh
sudo apt install -y cifs-utils     # für die NAS-Einbindung
```

**2. Programm auf den Server holen** – Repository klonen oder als ZIP herunterladen und entpacken,
z. B. nach `/opt/rechnungs-tinder`.

**3. Einstellungen festlegen:**

```sh
cd /opt/rechnungs-tinder
cp .env.beispiel .env
nano .env            # PIN, NAS-Adresse, Freigabe, Benutzer, Passwort eintragen
```

**4. Starten** – die NAS-Freigabe wird dabei direkt vom Container eingebunden:

```sh
sudo docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d --build
```

Fertig. Aufruf im Browser: `http://<IP-des-Servers>:8765`

> **Alternative:** Ist die NAS-Freigabe auf dem Server bereits eingebunden (z. B. über
> `/etc/fstab` unter `/mnt/nas/rechnungen`), reicht `RECHNUNGEN_ORDNER=/mnt/nas/rechnungen` in der
> `.env` und der Start mit `sudo docker compose up -d --build`. `PUID`/`PGID` müssen dann zu den
> Dateirechten dieses Ordners passen (`ls -ln /mnt/nas/rechnungen`).

**Nützliche Befehle** (im Ordner `/opt/rechnungs-tinder`):

| | |
|---|---|
| Läuft es? | `sudo docker compose ps` (Status *healthy*) |
| Protokoll ansehen | `sudo docker compose logs -f` |
| Neu starten | `sudo docker compose restart` |
| Stoppen | `sudo docker compose down` |
| Aktualisieren | neue Version holen (`git pull`), dann den Start-Befehl aus Schritt 4 wiederholen |

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
| Im Protokoll „Ordner … nicht erreichbar“ | NAS-Adresse/Freigabe/Benutzer/Passwort in der `.env` prüfen; `cifs-utils` installiert? Bei älteren NAS `SMB_VERSION=2.1` versuchen. |
| „Keine Berechtigung“ beim Verschieben oder bei Notizen | Der NAS-Benutzer braucht Schreibrechte; `PUID`/`PGID` passend setzen. |
| Rechnung ist „in einem anderen Programm geöffnet“ | Die PDF am PC schließen und erneut versuchen. |
| PIN vergessen | Steht in der `.env` (Docker) bzw. in den Argumenten der geplanten Aufgabe (Windows). |
