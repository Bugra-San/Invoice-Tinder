"""Einstellungen und zuletzt verwendete Ordner (in ~/.rechnungs-tinder-einstellungen.json)."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

DEFAULT_PATH = Path.home() / ".rechnungs-tinder-einstellungen.json"
MAX_RECENT = 5

DEFAULTS = {
    # Relativ zum Rechnungsordner oder ein absoluter Pfad.
    "bewilligt_ordner": "Bewilligt",
    "abgelehnt_ordner": "Abgelehnt",
    "letzte_ordner": [],
    # Netzwerk-Modus: nur diese Ordner (samt Unterordnern) sind vom Smartphone aus erreichbar.
    "freigaben": [],
}


class Settings:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.data = dict(DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass  # Einstellungen sind ein Komfort, kein Muss.

    @property
    def targets(self) -> dict[str, str]:
        return {
            "bewilligt": self.data.get("bewilligt_ordner") or DEFAULTS["bewilligt_ordner"],
            "abgelehnt": self.data.get("abgelehnt_ordner") or DEFAULTS["abgelehnt_ordner"],
        }

    @property
    def recent(self) -> list[str]:
        return [p for p in self.data.get("letzte_ordner", []) if isinstance(p, str) and Path(p).is_dir()]

    def remember(self, folder: str) -> None:
        recent = [p for p in self.data.get("letzte_ordner", []) if p != folder]
        self.data["letzte_ordner"] = [folder, *recent][:MAX_RECENT]
        self.save()

    @property
    def shares(self) -> list[str]:
        return [p for p in self.data.get("freigaben", []) if isinstance(p, str) and p.strip()]

    def pin(self, create: bool = False) -> str | None:
        """PIN für die Anmeldung im Netzwerk; wird bei Bedarf einmalig erzeugt."""
        pin = str(self.data.get("pin") or "").strip()
        if not pin and create:
            pin = f"{secrets.randbelow(10**6):06d}"
            self.data["pin"] = pin
            self.save()
        return pin or None

    def secret(self) -> str:
        """Geheimer Schlüssel zum Signieren der Anmelde-Tokens (bleibt über Neustarts gleich)."""
        secret = str(self.data.get("geheimschluessel") or "")
        if len(secret) < 32:
            secret = secrets.token_urlsafe(32)
            self.data["geheimschluessel"] = secret
            self.save()
        return secret
