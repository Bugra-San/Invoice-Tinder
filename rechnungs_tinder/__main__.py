"""Startet Rechnungs-Tinder und öffnet es im Browser.

    python -m rechnungs_tinder [--port 8765] [--kein-browser]
"""

from __future__ import annotations

import argparse
import logging
import socket
import threading
import webbrowser

from .app import create_app


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("Kein freier Port gefunden.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rechnungen per Wischen bewilligen oder ablehnen.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--kein-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = parser.parse_args()

    port = _free_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    app = create_app()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    print("=" * 60)
    print(" Rechnungs-Tinder läuft.")
    print(f" Adresse im Browser: {url}")
    print(" Dieses Fenster bitte geöffnet lassen.")
    print(" Zum Beenden dieses Fenster schließen (oder Strg+C).")
    print("=" * 60)

    if not args.kein_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
