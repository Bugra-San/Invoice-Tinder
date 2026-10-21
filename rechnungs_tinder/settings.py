"""Einstellungen und zuletzt verwendete Ordner (in ~/.rechnungs-tinder-einstellungen.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path.home() / ".rechnungs-tinder-einstellungen.json"
MAX_RECENT = 5

DEFAULTS = {
    # Relativ zum Rechnungsordner oder ein absoluter Pfad.
    "bewilligt_ordner": "Bewilligt",
    "abgelehnt_ordner": "Abgelehnt",
    "letzte_ordner": [],
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
