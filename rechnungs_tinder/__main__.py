"""Startet Rechnungs-Tinder.

    python -m rechnungs_tinder                     # nur auf diesem Rechner, Browser öffnet sich
    python -m rechnungs_tinder --netzwerk --ordner "D:\\Rechnungen"
                                                   # auch für Smartphones / Tablets im Netz
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from . import folders
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


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_flag(name: str) -> bool:
    return (_env(name, "") or "").lower() in ("1", "ja", "yes", "true", "an", "on")


def _env_list(name: str) -> list[str] | None:
    value = _env(name)
    return [p.strip() for p in value.split(";") if p.strip()] if value else None


def _serve(app, host: str, port: int, ssl_context) -> None:
    if ssl_context is None:
        try:
            from waitress import serve
        except ImportError:
            pass
        else:
            serve(app, host=host, port=port, threads=8, ident="Rechnungs-Tinder")
            return
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host=host, port=port, threaded=True, debug=False, ssl_context=ssl_context)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:  # Windows-Konsole: Umlaute/Sonderzeichen nie zum Absturz werden lassen
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) == 3 and sys.argv[1] == folders.DIALOG_FLAG:
        folders.run_native_dialog(sys.argv[2])  # Hilfsaufruf für das Ordner-Fenster (z. B. aus der .exe)
        return

    parser = argparse.ArgumentParser(
        description="Rechnungen per Wischen bewilligen oder ablehnen.",
        epilog="Alle Optionen lassen sich auch über Umgebungsvariablen setzen (RT_PORT, RT_ORDNER, "
        "RT_PIN, RT_EINSTELLUNGEN, RT_BEWILLIGT, RT_ABGELEHNT, RT_PROXY, RT_SERVER) – siehe docs/SERVER.md.",
    )
    parser.add_argument("--port", type=int, default=int(_env("RT_PORT", "8765")))
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument("--netzwerk", action="store_true",
                        help="Auch für Smartphones/Tablets im Netzwerk erreichbar machen (Anmeldung mit PIN)")
    parser.add_argument("--server", action="store_true", default=_env_flag("RT_SERVER"),
                        help="Dauerbetrieb auf einem Server (Netzwerk-Modus, kein Browser, fester Port)")
    parser.add_argument("--ordner", action="append", metavar="PFAD", default=_env_list("RT_ORDNER"),
                        help="Freigegebener Ordner für den Netzwerk-Modus (mehrfach möglich)")
    parser.add_argument("--pin", default=_env("RT_PIN"),
                        help="PIN für die Anmeldung (sonst aus den Einstellungen bzw. neu erzeugt)")
    parser.add_argument("--einstellungen", metavar="DATEI", default=_env("RT_EINSTELLUNGEN"),
                        help="Pfad der Einstellungsdatei")
    parser.add_argument("--hinter-proxy", action="store_true", default=_env_flag("RT_PROXY"),
                        help="Läuft hinter einem Reverse-Proxy (X-Forwarded-For/-Proto auswerten)")
    parser.add_argument("--zertifikat", metavar="DATEI", default=_env("RT_ZERTIFIKAT"),
                        help="TLS-Zertifikat (PEM) für HTTPS")
    parser.add_argument("--schluessel", metavar="DATEI", default=_env("RT_SCHLUESSEL"),
                        help="privater Schlüssel (PEM) zum Zertifikat")
    args = parser.parse_args()
    network = args.netzwerk or args.server

    settings = Settings(args.einstellungen)
    if args.pin and args.pin != settings.pin():
        settings.data["pin"] = args.pin
        settings.save()
    if args.ordner:
        # Freigaben merken, damit beim nächsten Mal "--netzwerk" allein reicht.
        settings.data["freigaben"] = [str(Path(p).expanduser().resolve()) for p in args.ordner]
        settings.save()
    for key, env in (("bewilligt_ordner", "RT_BEWILLIGT"), ("abgelehnt_ordner", "RT_ABGELEHNT")):
        if _env(env):
            settings.data[key] = _env(env)
    pin_was_set = bool(settings.pin())
    try:
        app = create_app(settings, network=network)
    except ValueError as exc:
        hint = ("Bitte RT_ORDNER setzen (z. B. RT_ORDNER=/rechnungen)." if args.server else
                'Bitte einmal mit dem Ordner starten, z. B.:  start-netzwerk.bat --ordner "D:\\Rechnungen"')
        sys.exit(f"Fehler: {exc}\n{hint}")
    for root in app.config["ROOTS"]:
        if not root.is_dir():
            print(f"WARNUNG: Der freigegebene Ordner {root} ist nicht erreichbar (NAS eingebunden?).", flush=True)
    if args.hinter_proxy:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    host = "0.0.0.0" if network else "127.0.0.1"
    port = args.port if args.server else _free_port(host, args.port)
    ssl_context = (args.zertifikat, args.schluessel) if args.zertifikat and args.schluessel else None
    scheme = "https" if ssl_context else "http"
    local_url = f"{scheme}://127.0.0.1:{port}/"

    print("=" * 64)
    print(" Rechnungs-Tinder läuft.")
    if args.server:
        print(f" Im Browser öffnen:  {scheme}://<Adresse-des-Servers>:{port}/")
        if not pin_was_set:
            print(f" Neu erzeugte PIN:   {app.config['PIN']}  (fest einstellen mit RT_PIN)")
    else:
        print(f" Auf diesem Computer: {local_url}")
    if network and not args.server:
        lan = [f"{scheme}://{ip}:{port}/" for ip in _lan_addresses()]
        print()
        print(" Auf dem Smartphone/Tablet (gleiches WLAN) im Browser öffnen:")
        for url in lan or ["(keine Netzwerkadresse gefunden)"]:
            print(f"     {url}")
        print(f" PIN zum Anmelden:   {app.config['PIN']}")
        if lan:
            _print_qr(lan[0])
    if network:
        print(" Freigegebene Ordner:")
        for root in app.config["ROOTS"]:
            print(f"     {root}")
    if not args.server:
        print()
        print(" Dieses Fenster bitte geöffnet lassen.")
        print(" Zum Beenden dieses Fenster schließen (oder Strg+C).")
    print("=" * 64, flush=True)

    if not (args.kein_browser or args.server):
        threading.Timer(1.0, webbrowser.open, args=(local_url,)).start()
    _serve(app, host, port, ssl_context)


if __name__ == "__main__":
    main()
