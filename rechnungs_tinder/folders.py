"""Ordnerauswahl: eingebauter Ordner-Browser und (falls vorhanden) das Windows-/System-Dialogfenster."""

from __future__ import annotations

import os
import string
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_NATIVE_DIALOG = r"""
import sys, tkinter
from tkinter import filedialog
root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askdirectory(title="Ordner mit Rechnungen auswählen", initialdir=sys.argv[1] or None)
root.destroy()
sys.stdout.write(path or "")
"""


@lru_cache(maxsize=1)
def native_dialog_available() -> bool:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return True


def pick_with_native_dialog(initial: str = "") -> str | None:
    """Öffnet den normalen Ordner-Dialog des Betriebssystems (in eigenem Prozess)."""
    if not native_dialog_available():
        return None
    result = subprocess.run(
        [sys.executable, "-c", _NATIVE_DIALOG, initial],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    path = result.stdout.strip()
    return str(Path(path).resolve()) if path else None


def _count_pdfs(path: Path) -> int:
    try:
        return sum(
            1 for e in path.iterdir() if e.is_file() and e.suffix.lower() == ".pdf" and not e.name.startswith(".")
        )
    except OSError:
        return 0


def shortcuts() -> list[dict]:
    """Startpunkte für den eingebauten Ordner-Browser."""
    home = Path.home()
    entries = [("Persönlicher Ordner", home)]
    for label, names in (
        ("Schreibtisch", ("Desktop", "Schreibtisch")),
        ("Dokumente", ("Documents", "Dokumente")),
        ("Downloads", ("Downloads",)),
    ):
        for name in names:
            if (home / name).is_dir():
                entries.append((label, home / name))
                break
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:\\")
            if drive.exists():
                entries.append((f"Laufwerk {letter}:", drive))
    else:
        entries.append(("Gesamter Computer", Path("/")))
    return [{"name": label, "pfad": str(path)} for label, path in entries]


def is_within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def browse(path: str | None, roots: list[Path] | None = None) -> dict:
    """Listet die Unterordner eines Ordners für den eingebauten Browser.

    Mit ``roots`` (Netzwerk-Modus) sind nur diese Ordner und ihre Unterordner sichtbar.
    """
    if not path:
        start = [{"name": r.name or str(r), "pfad": str(r)} for r in roots] if roots else shortcuts()
        return {"pfad": None, "oben": None, "ordner": start, "pdfs": 0}
    folder = Path(path).expanduser().resolve()
    if roots and not is_within(folder, roots):
        raise PermissionError(path)
    if not folder.is_dir():
        raise FileNotFoundError(path)
    dirs = []
    try:
        for entry in folder.iterdir():
            try:
                if entry.is_dir() and not entry.name.startswith(".") and not entry.name.startswith("$"):
                    dirs.append({"name": entry.name, "pfad": str(entry)})
            except OSError:
                continue
    except PermissionError:
        pass
    dirs.sort(key=lambda d: d["name"].casefold())
    parent = folder.parent
    if parent == folder or (roots and not is_within(parent, roots)):
        up = ""  # zurück zur Übersicht der Startpunkte
    else:
        up = str(parent)
    return {"pfad": str(folder), "oben": up, "ordner": dirs, "pdfs": _count_pdfs(folder)}
