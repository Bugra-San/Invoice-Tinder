"""Webserver: liefert die Oberfläche und die API (``/api/v1``) für Browser und Apps.

Zwei Betriebsarten:

* **lokal** (Standard): Server nur auf diesem Rechner erreichbar; der Browser bekommt
  den Zugangsschlüssel automatisch mit der Startseite.
* **Netzwerk**: Smartphones/Tablets/Apps im Netz melden sich mit einer PIN an und
  erhalten einen Zugangsschlüssel (Token). Erreichbar sind nur die freigegebenen Ordner.

Die API ist in ``docs/API.md`` beschrieben.
"""

from __future__ import annotations

import hmac
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import folders
from .core import InvoiceError, InvoiceFolder
from .settings import Settings

API_VERSION = 1
STATIC_DIR = Path(__file__).parent / "static"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOOPBACK_ADDRS = {"127.0.0.1", "::1"}

TOKEN_MAX_AGE = 180 * 24 * 3600  # Anmeldung gilt ein halbes Jahr
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 300


class AuthError(Exception):
    """Nicht (mehr) angemeldet."""


class AccessError(InvoiceError):
    """Ordner liegt außerhalb der Freigaben."""


def _hostname(host: str) -> str:
    if host.startswith("["):
        return host[1 : host.find("]")]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def create_app(
    settings: Settings | None = None,
    *,
    network: bool = False,
    shares: list[str] | None = None,
    pin: str | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    settings = settings or Settings()
    # Freigaben gelten im Netzwerk-Modus; am eigenen Rechner ist jeder Ordner erlaubt.
    if shares is None:
        shares = settings.shares if network else []
    roots = [Path(p).expanduser().resolve() for p in shares]
    if network and not roots:
        raise ValueError("Im Netzwerk-Modus muss mindestens ein Ordner freigegeben sein.")
    if network:
        pin = pin or settings.pin(create=True)
    # Ändert sich die PIN, werden alle bisherigen Anmeldungen ungültig.
    signer = URLSafeTimedSerializer(settings.secret() + (pin or ""), salt="rechnungs-tinder-token")
    app.config.update(NETWORK=network, PIN=pin, ROOTS=roots)

    cache: dict[str, InvoiceFolder] = {}
    cache_lock = threading.Lock()
    failures: dict[str, list[float]] = {}

    # ------------------------------------------------------------ Hilfen

    def is_local_request() -> bool:
        # Auch der Host-Name muss lokal sein (Schutz gegen DNS-Rebinding).
        return request.remote_addr in LOOPBACK_ADDRS and _hostname(request.host) in LOOPBACK_HOSTS

    def given_token() -> str | None:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return request.headers.get("X-Token") or request.args.get("t")

    def token_valid(token: str | None) -> bool:
        if not token:
            return False
        try:
            signer.loads(token, max_age=TOKEN_MAX_AGE)
            return True
        except BadSignature:
            return False

    def allowed(path: Path) -> bool:
        return not roots or folders.is_within(path, roots)

    def get_folder(path: str | None) -> InvoiceFolder:
        path = str(path or "").strip()
        if not path:
            raise InvoiceError("Bitte zuerst einen Ordner auswählen.")
        resolved = Path(path).expanduser().resolve()
        if not allowed(resolved):
            raise AccessError("Auf diesen Ordner haben Sie keinen Zugriff.")
        key = str(resolved)
        with cache_lock:
            folder = cache.get(key)
            if folder is None or not folder.folder.is_dir():
                folder = InvoiceFolder(key, settings.targets)
                cache[key] = folder
            return folder

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise InvoiceError("Ungültige Anfrage.")
        return data

    def folder_from_body(data: dict) -> InvoiceFolder:
        return get_folder(data.get("ordner"))

    def recent() -> list[str]:
        return [p for p in settings.recent if allowed(Path(p))]

    # -------------------------------------------------------- Zugriffsschutz

    @app.before_request
    def protect():
        if not request.path.startswith("/api/"):
            return None
        if request.path in ("/api/v1/info", "/api/v1/anmelden"):
            return None
        if not token_valid(given_token()):
            raise AuthError()
        return None

    @app.errorhandler(AuthError)
    def auth_error(_exc):
        return jsonify({"fehler": "Bitte melden Sie sich an.", "code": "anmeldung"}), 401

    @app.errorhandler(AccessError)
    def access_error(exc):
        return jsonify({"fehler": str(exc), "code": "kein_zugriff"}), 403

    @app.errorhandler(InvoiceError)
    def invoice_error(exc):
        return jsonify({"fehler": str(exc)}), 400

    @app.after_request
    def headers(resp: Response):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    # ------------------------------------------------------------ Oberfläche

    @app.get("/")
    def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        # Auf dem eigenen Rechner ist keine Anmeldung nötig.
        token = signer.dumps({"lokal": True}) if is_local_request() else ""
        resp = Response(html.replace("__TOKEN__", token), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_file(STATIC_DIR / "manifest.webmanifest", mimetype="application/manifest+json")

    # ------------------------------------------------------------------- API

    @app.get("/api/v1/info")
    def info():
        logged_in = token_valid(given_token())
        local = is_local_request()
        return jsonify({
            "app": "Rechnungs-Tinder",
            "api": API_VERSION,
            "netzwerk": network,
            "angemeldet": logged_in,
            "systemdialog": logged_in and local and folders.native_dialog_available(),
            "letzte_ordner": recent() if logged_in else [],
            "freigaben": [str(r) for r in roots] if logged_in else [],
        })

    @app.post("/api/v1/anmelden")
    def login():
        if not network:
            raise InvoiceError("Anmeldung ist nur im Netzwerk-Modus nötig.")
        addr = request.remote_addr or "?"
        now = time.monotonic()
        recent_failures = [t for t in failures.get(addr, []) if now - t < LOGIN_LOCK_SECONDS]
        if len(recent_failures) >= LOGIN_MAX_FAILURES:
            return jsonify({"fehler": "Zu viele falsche Versuche. Bitte warten Sie 5 Minuten."}), 429
        entered = str((request.get_json(silent=True) or {}).get("pin", "")).strip()
        if not hmac.compare_digest(entered.encode(), (pin or "").encode()):
            failures[addr] = [*recent_failures, now]
            return jsonify({"fehler": "Die PIN ist falsch."}), 401
        failures.pop(addr, None)
        return jsonify({"token": signer.dumps({"geraet": str(request.headers.get("User-Agent", ""))[:80]})})

    @app.get("/api/v1/durchsuchen")
    def browse():
        try:
            return jsonify(folders.browse(request.args.get("pfad"), roots or None))
        except (FileNotFoundError, NotADirectoryError):
            raise InvoiceError("Dieser Ordner wurde nicht gefunden.")
        except PermissionError:
            raise AccessError("Auf diesen Ordner haben Sie keinen Zugriff.")

    @app.post("/api/v1/systemdialog")
    def native_dialog():
        if not is_local_request():
            raise InvoiceError("Das Ordner-Fenster gibt es nur am Computer selbst.")
        initial = str(roots[0]) if roots else ""
        path = folders.pick_with_native_dialog(initial)
        if path and not allowed(Path(path)):
            raise AccessError("Auf diesen Ordner haben Sie keinen Zugriff.")
        return jsonify({"pfad": path})

    @app.get("/api/v1/ordner")
    def folder_status():
        return jsonify({"status": get_folder(request.args.get("pfad")).status()})

    @app.post("/api/v1/ordner")
    def open_folder():
        folder = get_folder(body().get("pfad"))
        settings.remember(str(folder.folder))
        return jsonify({"status": folder.status(), "letzte_ordner": recent()})

    @app.get("/api/v1/rechnung")
    def invoice_info():
        return jsonify(get_folder(request.args.get("ordner")).info(request.args.get("name", "")))

    @app.get("/api/v1/seite")
    def page_image():
        try:
            page = int(request.args.get("seite", 0))
            width = int(float(request.args.get("breite", 800)))
        except ValueError:
            raise InvoiceError("Ungültige Anfrage.")
        image = get_folder(request.args.get("ordner")).render(request.args.get("name", ""), page, width)
        resp = Response(image, mimetype="image/jpeg")
        # Die URL enthält die Dateiversion, daher darf zwischengespeichert werden.
        resp.headers["Cache-Control"] = "private, max-age=3600"
        return resp

    @app.get("/api/v1/datei")
    def download():
        folder = get_folder(request.args.get("ordner"))
        path = folder.path_of(request.args.get("name", ""))
        resp = send_file(path, mimetype="application/pdf", download_name=path.name, max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/v1/entscheiden")
    def decide():
        data = body()
        folder = folder_from_body(data)
        folder.decide(str(data.get("name", "")), str(data.get("entscheidung", "")))
        return jsonify({"status": folder.status()})

    @app.post("/api/v1/rueckgaengig")
    def undo():
        folder = folder_from_body(body())
        name = folder.undo()
        return jsonify({"name": name, "status": folder.status()})

    @app.post("/api/v1/notiz")
    def note():
        data = body()
        folder = folder_from_body(data)
        name = str(data.get("name", ""))
        xref = folder.add_note(name, int(data.get("seite", 0)), data.get("x", 0), data.get("y", 0), str(data.get("text", "")))
        return jsonify({"xref": xref, "version": folder.version_of(name)})

    @app.post("/api/v1/zeichnung")
    def ink():
        data = body()
        folder = folder_from_body(data)
        name = str(data.get("name", ""))
        xref = folder.add_ink(name, int(data.get("seite", 0)), data.get("striche") or [])
        return jsonify({"xref": xref, "version": folder.version_of(name)})

    @app.post("/api/v1/anmerkung-loeschen")
    def delete_annotation():
        data = body()
        folder = folder_from_body(data)
        name = str(data.get("name", ""))
        folder.delete_annotation(name, int(data.get("seite", 0)), int(data.get("xref", 0)))
        return jsonify({"version": folder.version_of(name)})

    @app.post("/api/v1/verschieben")
    def move():
        folder = folder_from_body(body())
        result = folder.move_decided()
        return jsonify({"ergebnis": result, "status": folder.status()})

    return app
