# Rechnungs-Tinder – API (Version 1)

Diese Schnittstelle benutzt die Browser-Oberfläche – und sie ist die Grundlage für eine spätere
**eigene iOS-App**. Die App braucht keinen eigenen Server: Sie spricht mit dem Rechnungs-Tinder,
der auf dem Rechner/Server mit dem Rechnungsordner läuft (Netzwerk-Modus, siehe README).

- Basis-URL: `http(s)://<server>:<port>/api/v1/`
- Daten: JSON (UTF-8), Seitenbilder als JPEG, Originaldateien als PDF
- Fehler: HTTP-Status ≥ 400 mit `{"fehler": "verständliche deutsche Meldung", "code": "…"}`
  (`code` optional: `anmeldung` = neu anmelden, `kein_zugriff` = Ordner nicht freigegeben)
- Pfade (`ordner`, `pfad`) sind Pfade **auf dem Server**, so wie sie die API selbst liefert.
  Erreichbar sind nur die freigegebenen Ordner und ihre Unterordner.

## Anmeldung

| | |
|---|---|
| `GET  info` | ohne Anmeldung. `{app, api: 1, netzwerk, angemeldet, systemdialog, letzte_ordner, freigaben}` |
| `POST anmelden` | `{"pin": "123456"}` → `{"token": "…"}` · falsche PIN: 401 · nach 5 Fehlversuchen 5 Minuten Sperre: 429 |

Der Token wird bei allen weiteren Anfragen mitgeschickt:

```
Authorization: Bearer <token>
```

Für Bild-URLs (wo keine Header möglich sind) geht auch der Parameter `?t=<token>`.
Ein Token gilt 180 Tage. Ändert der Betreiber die PIN, werden alle Tokens ungültig (Antwort 401,
`code: "anmeldung"` → App zeigt wieder die PIN-Eingabe). Die App sollte den Token in der
**Keychain** speichern.

## Ordner

| | |
|---|---|
| `GET  durchsuchen?pfad=…` | Unterordner auflisten. Ohne `pfad`: die Startpunkte (Freigaben). → `{pfad, oben, ordner: [{name, pfad}], pdfs}` · `oben == ""` heißt: zurück zu den Startpunkten |
| `POST ordner` | `{"pfad": …}` Ordner öffnen (wird als „zuletzt verwendet“ gemerkt) → `{status, letzte_ordner}` |
| `GET  ordner?pfad=…` | aktuellen Stand abfragen → `{status}` |

`status`:

```json
{
  "ordner": "/srv/rechnungen/Oktober",
  "ordnername": "Oktober",
  "rechnungen": [
    {"name": "Rechnung 1.pdf", "entscheidung": null,        "version": "1729500000000000000-48211"},
    {"name": "Rechnung 2.pdf", "entscheidung": "bewilligt", "version": "…"}
  ],
  "ziele": {"bewilligt": "/srv/rechnungen/Oktober/Bewilligt", "abgelehnt": "…/Abgelehnt"}
}
```

Die nächste zu prüfende Rechnung ist die **erste mit `entscheidung: null`**. `version` ändert sich,
sobald die Datei geändert wurde (z. B. durch eine Notiz) – ideal als Cache-Schlüssel.

## Rechnungen

| | |
|---|---|
| `GET  rechnung?ordner=…&name=…` | `{name, version, seiten: [{breite, hoehe}]}` (Seitengröße in PDF-Punkten, so wie angezeigt) |
| `GET  seite?ordner=…&name=…&seite=0&breite=1170&v=<version>` | Seite als JPEG in der gewünschten Pixelbreite (50–3500) inkl. aller Anmerkungen. Für ein iPhone: Anzeigebreite × Bildschirm-Skalierung (z. B. 390 × 3). Darf zwischengespeichert werden. |
| `GET  datei?ordner=…&name=…` | Original-PDF (z. B. für PDFKit oder „Teilen“) |

## Entscheiden

| | |
|---|---|
| `POST entscheiden` | `{"ordner", "name", "entscheidung": "bewilligt" \| "abgelehnt"}` → `{status}` |
| `POST rueckgaengig` | `{"ordner"}` nimmt die zuletzt getroffene Entscheidung zurück → `{name, status}` |
| `POST verschieben` | `{"ordner"}` verschiebt alle entschiedenen Rechnungen → `{ergebnis: {verschoben: {bewilligt: [...], abgelehnt: [...]}, fehler: [{name, fehler}], ziele}, status}` |

Entscheidungen werden auf dem Server im Ordner gespeichert. Mehrere Geräte können am selben
Ordner arbeiten; nach jeder Aktion liefert der Server den aktuellen `status`.

## Anmerkungen

Koordinaten sind **relativ zur angezeigten Seite**: `x`, `y` zwischen 0 und 1, Ursprung oben links
(unabhängig von Zoom, Bildgröße und Seitendrehung).

| | |
|---|---|
| `POST notiz` | `{"ordner", "name", "seite", "x", "y", "text"}` → `{xref, version}` – sichtbare Textnotiz, linke obere Ecke an (x, y) |
| `POST zeichnung` | `{"ordner", "name", "seite", "striche": [[[x, y], [x, y], …], …]}` → `{xref, version}` – Freihandlinie(n) |
| `POST anmerkung-loeschen` | `{"ordner", "name", "seite", "xref"}` → `{version}` |

Anmerkungen werden sofort als normale PDF-Anmerkungen in die Datei geschrieben.

## Hinweise für die iOS-App

- **Ablauf:** `info` → ggf. PIN-Eingabe + `anmelden` → `durchsuchen` / `letzte_ordner` →
  `POST ordner` → Karten mit `seite` (Seite 0) anzeigen → `entscheiden` per Swipe → wenn keine
  offene Rechnung mehr da ist: Zusammenfassung → `verschieben`.
- **Darstellung:** Für Karten und Detailansicht reichen die JPEG-Seiten (`seite`) – damit bleibt die
  App klein, und Rendering/Anmerkungen sind auf allen Geräten gleich. Alternativ kann die App das
  Original über `datei` mit PDFKit anzeigen.
- **Netzwerk:** Im Heimnetz läuft der Server standardmäßig per HTTP. Dafür braucht die App
  `NSAllowsLocalNetworking` (App Transport Security) und `NSLocalNetworkUsageDescription`
  in der `Info.plist`. Für Zugriff von unterwegs: HTTPS (`--zertifikat`/`--schluessel`) und
  Erreichbarkeit z. B. über VPN – den Server nicht ungeschützt ins Internet stellen.
- **Server finden:** Adresse und PIN zeigt das Programm-Fenster beim Start an (mit `pip install qrcode`
  auch als QR-Code, den die App einscannen kann).
