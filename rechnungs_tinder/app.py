"""Lokaler Webserver: liefert die Oberfläche und die API für den Browser."""

from __future__ import annotations

import secrets
import threading
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

from . import folders
from .core import InvoiceError, InvoiceFolder
from .settings import Settings

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def create_app(settings: Settings | None = None, token: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    settings = settings or Settings()
    token = token or secrets.token_urlsafe(24)
    app.config["TOKEN"] = token
    state: dict = {"folder": None}
    lock = threading.Lock()

    def current() -> InvoiceFolder:
        if state["folder"] is None:
            raise InvoiceError("Bitte zuerst einen Ordner auswählen.")
        return state["folder"]

    @app.before_request
    def protect():
        # Nur Zugriffe vom eigenen Rechner, nur mit dem Schlüssel aus der Startseite.
        host = request.host.rsplit(":", 1)[0] if not request.host.endswith("]") else request.host
        if host not in ALLOWED_HOSTS:
            abort(403)
        if request.path.startswith("/api/"):
            given = request.headers.get("X-Token") or request.args.get("t")
            if not given or not secrets.compare_digest(given, token):
                abort(403)

    @app.errorhandler(InvoiceError)
    def invoice_error(exc: InvoiceError):
        return jsonify({"fehler": str(exc)}), 400

    @app.get("/")
    def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        resp = Response(html.replace("__TOKEN__", token), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise InvoiceError("Ungültige Anfrage.")
        return data

    def status_payload() -> dict:
        folder = state["folder"]
        return {
            "status": folder.status() if folder else None,
            "letzte_ordner": settings.recent,
            "systemdialog": folders.native_dialog_available(),
        }

    @app.get("/api/status")
    def status():
        return jsonify(status_payload())

    @app.post("/api/ordner")
    def open_folder():
        path = str(body().get("pfad") or "").strip()
        if not path:
            raise InvoiceError("Bitte einen Ordner auswählen.")
        folder = InvoiceFolder(path, settings.targets)
        with lock:
            state["folder"] = folder
        settings.remember(str(folder.folder))
        return jsonify(status_payload())

    @app.get("/api/durchsuchen")
    def browse():
        try:
            return jsonify(folders.browse(request.args.get("pfad")))
        except (FileNotFoundError, NotADirectoryError):
            raise InvoiceError("Dieser Ordner wurde nicht gefunden.")
        except PermissionError:
            raise InvoiceError("Auf diesen Ordner haben Sie keinen Zugriff.")

    @app.post("/api/systemdialog")
    def native_dialog():
        initial = state["folder"].folder if state["folder"] else ""
        return jsonify({"pfad": folders.pick_with_native_dialog(str(initial))})

    @app.get("/api/rechnung")
    def invoice_info():
        return jsonify(current().info(request.args.get("name", "")))

    @app.get("/api/seite")
    def page_image():
        try:
            page = int(request.args.get("seite", 0))
            width = int(float(request.args.get("breite", 800)))
        except ValueError:
            raise InvoiceError("Ungültige Anfrage.")
        image = current().render(request.args.get("name", ""), page, width)
        resp = Response(image, mimetype="image/jpeg")
        # Die URL enthält die Dateiversion, daher darf der Browser zwischenspeichern.
        resp.headers["Cache-Control"] = "private, max-age=3600"
        return resp

    @app.post("/api/entscheiden")
    def decide():
        data = body()
        current().decide(str(data.get("name", "")), str(data.get("entscheidung", "")))
        return jsonify(status_payload())

    @app.post("/api/rueckgaengig")
    def undo():
        name = current().undo()
        return jsonify({"name": name, **status_payload()})

    @app.post("/api/notiz")
    def note():
        data = body()
        name = str(data.get("name", ""))
        folder = current()
        xref = folder.add_note(name, int(data.get("seite", 0)), data.get("x", 0), data.get("y", 0), str(data.get("text", "")))
        return jsonify({"xref": xref, "version": folder.version_of(name)})

    @app.post("/api/zeichnung")
    def ink():
        data = body()
        name = str(data.get("name", ""))
        folder = current()
        xref = folder.add_ink(name, int(data.get("seite", 0)), data.get("striche") or [])
        return jsonify({"xref": xref, "version": folder.version_of(name)})

    @app.post("/api/anmerkung-loeschen")
    def delete_annotation():
        data = body()
        name = str(data.get("name", ""))
        folder = current()
        folder.delete_annotation(name, int(data.get("seite", 0)), int(data.get("xref", 0)))
        return jsonify({"version": folder.version_of(name)})

    @app.post("/api/verschieben")
    def move():
        result = current().move_decided()
        return jsonify({"ergebnis": result, **status_payload()})

    return app
