"""Startet Rechnungs-Tinder.

    python -m rechnungs_tinder                     # nur auf diesem Rechner, Browser öffnet sich
    python -m rechnungs_tinder --netzwerk --ordner "D:\\Rechnungen"
                                                   # auch für Smartphones / Tablets im Netz
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .app import create_app
from .settings import Settings


def _free_port(host: str, preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("Kein freier Port gefunden.")


def _lan_addresses() -> list[str]:
    """IP-Adressen, unter denen der Rechner im Heim-/Firmennetz erreichbar ist."""
    addrs: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # es wird nichts gesendet
            addrs.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in addrs and not ip.startswith("127."):
                addrs.append(ip)
    except OSError:
        pass
    return addrs


def _print_qr(url: str) -> None:
    try:
        import qrcode  # optional: pip install qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rechnungen per Wischen bewilligen oder ablehnen.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--netzwerk", action="store_true",
                        help="Auch für Smartphones/Tablets im Netzwerk erreichbar machen (Anmeldung mit PIN)")
    parser.add_argument("--ordner", action="append", metavar="PFAD",
                        help="Freigegebener Ordner für den Netzwerk-Modus (mehrfach möglich)")
    parser.add_argument("--pin", help="PIN für die Anmeldung (sonst aus den Einstellungen bzw. neu erzeugt)")
    parser.add_argument("--zertifikat", metavar="DATEI", help="TLS-Zertifikat (PEM) für HTTPS")
    parser.add_argument("--schluessel", metavar="DATEI", help="privater Schlüssel (PEM) zum Zertifikat")
    args = parser.parse_args()

    settings = Settings()
    if args.pin:
        settings.data["pin"] = args.pin
        settings.save()
    if args.ordner:
        # Freigaben merken, damit beim nächsten Mal "--netzwerk" allein reicht.
        settings.data["freigaben"] = [str(Path(p).expanduser().resolve()) for p in args.ordner]
        settings.save()
    try:
        app = create_app(settings, network=args.netzwerk)
    except ValueError as exc:
        sys.exit(
            f"Fehler: {exc}\n"
            'Bitte einmal mit dem Ordner starten, z. B.:  start-netzwerk.bat --ordner "D:\\Rechnungen"'
        )

    host = "0.0.0.0" if args.netzwerk else "127.0.0.1"
    port = _free_port(host, args.port)
    ssl_context = (args.zertifikat, args.schluessel) if args.zertifikat and args.schluessel else None
    scheme = "https" if ssl_context else "http"
    local_url = f"{scheme}://127.0.0.1:{port}/"
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    print("=" * 64)
    print(" Rechnungs-Tinder läuft.")
    print(f" Auf diesem Computer: {local_url}")
    if args.netzwerk:
        lan = [f"{scheme}://{ip}:{port}/" for ip in _lan_addresses()]
        print()
        print(" Auf dem Smartphone/Tablet (gleiches WLAN) im Browser öffnen:")
        for url in lan or ["(keine Netzwerkadresse gefunden)"]:
            print(f"     {url}")
        print(f" PIN zum Anmelden:   {app.config['PIN']}")
        print(" Freigegebene Ordner:")
        for root in app.config["ROOTS"]:
            print(f"     {root}")
        if lan:
            _print_qr(lan[0])
    print()
    print(" Dieses Fenster bitte geöffnet lassen.")
    print(" Zum Beenden dieses Fenster schließen (oder Strg+C).")
    print("=" * 64)

    if not args.kein_browser:
        threading.Timer(1.0, webbrowser.open, args=(local_url,)).start()
    app.run(host=host, port=port, threaded=True, debug=False, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
