"""Kernlogik: Rechnungen einlesen, Entscheidungen merken, Anmerkungen
in die PDF schreiben und am Ende in die Zielordner verschieben."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

import pymupdf

APPROVED = "bewilligt"
REJECTED = "abgelehnt"
DECISIONS = (APPROVED, REJECTED)

STATE_FILE = ".rechnungs-tinder.json"
DEFAULT_TARGETS = {APPROVED: "Bewilligt", REJECTED: "Abgelehnt"}

# Obergrenze für gerenderte Seitenbilder (Breite in Pixeln).
MAX_RENDER_WIDTH = 3500
MIN_RENDER_WIDTH = 50

NOTE_TEXT_COLOR = (0.75, 0.0, 0.0)
NOTE_FILL_COLOR = (1.0, 0.97, 0.7)
INK_COLOR = (0.85, 0.0, 0.0)


class InvoiceError(Exception):
    """Fehler mit einer verständlichen Meldung für die Oberfläche."""


def _natural_key(name: str):
    return [int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", name)]


def _unique_destination(directory: Path, name: str) -> Path:
    dest = directory / name
    stem, suffix = os.path.splitext(name)
    n = 2
    while dest.exists():
        dest = directory / f"{stem} ({n}){suffix}"
        n += 1
    return dest


def _wrap_text(text: str, fontsize: float, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}" if current else word
            if pymupdf.get_text_length(candidate, fontname="helv", fontsize=fontsize) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines


class InvoiceFolder:
    """Ein ausgewählter Ordner mit Rechnungen (PDF-Dateien)."""

    def __init__(self, folder: str | os.PathLike, targets: dict[str, str] | None = None):
        self.folder = Path(folder).expanduser().resolve()
        if not self.folder.is_dir():
            raise InvoiceError(f"Der Ordner „{folder}“ wurde nicht gefunden.")
        targets = targets or {}
        self.targets = {
            key: self._resolve_target(targets.get(key) or DEFAULT_TARGETS[key])
            for key in DECISIONS
        }
        for target in self.targets.values():
            if target == self.folder:
                raise InvoiceError("Der Zielordner darf nicht der Ausgangsordner sein.")
        self._lock = threading.RLock()
        self.decisions: dict[str, str] = self._load_state()

    # ------------------------------------------------------------------ Ordner

    def _resolve_target(self, value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.folder / path
        return path.resolve()

    @property
    def state_path(self) -> Path:
        return self.folder / STATE_FILE

    def _load_state(self) -> dict[str, str]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        decisions = data.get("entscheidungen", {}) if isinstance(data, dict) else {}
        existing = set(self.invoices())
        return {
            name: decision
            for name, decision in decisions.items()
            if name in existing and decision in DECISIONS
        }

    def _save_state(self) -> None:
        if not self.decisions:
            self.state_path.unlink(missing_ok=True)
            return
        data = {"version": 1, "entscheidungen": self.decisions}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def invoices(self) -> list[str]:
        """Alle PDF-Dateien direkt im Ordner, natürlich sortiert."""
        names = [
            entry.name
            for entry in self.folder.iterdir()
            if entry.is_file()
            and entry.suffix.lower() == ".pdf"
            and not entry.name.startswith(".")
        ]
        return sorted(names, key=_natural_key)

    def path_of(self, name: str) -> Path:
        if not name or Path(name).name != name or name.startswith("."):
            raise InvoiceError("Ungültiger Dateiname.")
        path = self.folder / name
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise InvoiceError(f"Die Rechnung „{name}“ wurde nicht gefunden.")
        return path

    def version_of(self, name: str) -> str:
        """Ändert sich bei jeder Änderung der Datei (für den Browser-Zwischenspeicher)."""
        st = self.path_of(name).stat()
        return f"{st.st_mtime_ns}-{st.st_size}"

    def status(self) -> dict:
        with self._lock:
            invoices = self.invoices()
            # Entscheidungen zu inzwischen verschwundenen Dateien verwerfen.
            stale = [n for n in self.decisions if n not in invoices]
            for name in stale:
                del self.decisions[name]
            if stale:
                self._save_state()
            items = [
                {"name": n, "entscheidung": self.decisions.get(n), "version": self.version_of(n)}
                for n in invoices
            ]
            return {
                "ordner": str(self.folder),
                "ordnername": self.folder.name or str(self.folder),
                "rechnungen": items,
                "ziele": {k: str(v) for k, v in self.targets.items()},
            }

    # ------------------------------------------------------------- Entscheiden

    def decide(self, name: str, decision: str) -> None:
        if decision not in DECISIONS:
            raise InvoiceError("Unbekannte Entscheidung.")
        self.path_of(name)
        with self._lock:
            self.decisions.pop(name, None)  # ans Ende der Reihenfolge setzen
            self.decisions[name] = decision
            self._save_state()

    def undo(self) -> str | None:
        """Nimmt die zuletzt getroffene Entscheidung zurück."""
        with self._lock:
            if not self.decisions:
                return None
            name = next(reversed(self.decisions))
            del self.decisions[name]
            self._save_state()
            return name

    def move_decided(self) -> dict:
        """Verschiebt alle entschiedenen Rechnungen in ihre Zielordner."""
        with self._lock:
            moved = {key: [] for key in DECISIONS}
            errors = []
            for name, decision in list(self.decisions.items()):
                source = self.folder / name
                if not source.is_file():
                    del self.decisions[name]
                    continue
                try:
                    target_dir = self.targets[decision]
                    target_dir.mkdir(parents=True, exist_ok=True)
                    dest = _unique_destination(target_dir, name)
                    shutil.move(str(source), str(dest))
                except OSError as exc:
                    errors.append({"name": name, "fehler": _friendly_os_error(exc)})
                    continue
                moved[decision].append(dest.name)
                del self.decisions[name]
            self._save_state()
            return {
                "verschoben": moved,
                "fehler": errors,
                "ziele": {k: str(v) for k, v in self.targets.items()},
            }

    # ------------------------------------------------------------- PDF-Zugriff

    def _open(self, name: str) -> pymupdf.Document:
        path = self.path_of(name)
        try:
            doc = pymupdf.open(path)
        except Exception as exc:  # beschädigte Datei o. ä.
            raise InvoiceError(f"Die Datei „{name}“ kann nicht geöffnet werden.") from exc
        if doc.needs_pass:
            doc.close()
            raise InvoiceError(f"Die Datei „{name}“ ist mit einem Passwort geschützt.")
        return doc

    def _page(self, doc: pymupdf.Document, page: int) -> pymupdf.Page:
        if not 0 <= page < doc.page_count:
            raise InvoiceError("Diese Seite gibt es nicht.")
        return doc[page]

    def info(self, name: str) -> dict:
        with self._lock, self._open(name) as doc:
            pages = [{"breite": p.rect.width, "hoehe": p.rect.height} for p in doc]
        return {"name": name, "seiten": pages, "version": self.version_of(name)}

    def render(self, name: str, page: int, width: int) -> bytes:
        """Rendert eine Seite (inkl. Anmerkungen) als JPEG mit der gewünschten Breite."""
        width = max(MIN_RENDER_WIDTH, min(MAX_RENDER_WIDTH, int(width)))
        with self._lock, self._open(name) as doc:
            pg = self._page(doc, page)
            zoom = width / pg.rect.width
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True, alpha=False)
            return pix.tobytes(output="jpeg", jpg_quality=88)

    def _to_page_point(self, pg: pymupdf.Page, x: float, y: float) -> pymupdf.Point:
        """Wandelt relative Bildkoordinaten (0..1) in PDF-Koordinaten um."""
        x = min(max(float(x), 0.0), 1.0)
        y = min(max(float(y), 0.0), 1.0)
        shown = pymupdf.Point(x * pg.rect.width, y * pg.rect.height)
        return shown * pg.derotation_matrix

    def _save(self, doc: pymupdf.Document, name: str) -> None:
        path = self.path_of(name)
        try:
            if doc.can_save_incrementally():
                doc.saveIncr()
                return
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=self.folder, prefix=".tmp-")
            os.close(fd)
            try:
                doc.save(tmp, garbage=1, deflate=True)
                doc.close()
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        except (OSError, RuntimeError, ValueError) as exc:
            raise InvoiceError(
                f"Die Anmerkung konnte nicht gespeichert werden. Ist „{name}“ "
                "vielleicht in einem anderen Programm geöffnet?"
            ) from exc

    def add_note(self, name: str, page: int, x: float, y: float, text: str) -> int:
        """Schreibt eine sichtbare Text-Notiz an die angetippte Stelle."""
        text = (text or "").strip()
        if not text:
            raise InvoiceError("Die Notiz ist leer.")
        with self._lock:
            doc = self._open(name)
            try:
                pg = self._page(doc, page)
                shown_w, shown_h = pg.rect.width, pg.rect.height
                fontsize = max(10.0, round(min(shown_w, shown_h) / 45, 1))
                pad = fontsize * 0.5
                lines = _wrap_text(text, fontsize, shown_w * 0.45)
                text_w = max(pymupdf.get_text_length(l, fontname="helv", fontsize=fontsize) for l in lines)
                box_w = min(shown_w, text_w + 2 * pad + fontsize * 2)
                box_h = min(shown_h, len(lines) * fontsize * 1.25 + 2 * pad)
                # Box in Anzeige-Koordinaten so verschieben, dass sie auf die Seite passt.
                left = min(max(float(x), 0.0) * shown_w, shown_w - box_w)
                top = min(max(float(y), 0.0) * shown_h, shown_h - box_h)
                corners = [
                    self._to_page_point(pg, left / shown_w, top / shown_h),
                    self._to_page_point(pg, (left + box_w) / shown_w, (top + box_h) / shown_h),
                ]
                rect = pymupdf.Rect(corners[0], corners[0]) | corners[1]
                annot = pg.add_freetext_annot(
                    rect,
                    "\n".join(lines),
                    fontsize=fontsize,
                    fontname="helv",
                    text_color=NOTE_TEXT_COLOR,
                    fill_color=NOTE_FILL_COLOR,
                    border_width=1,
                    rotate=pg.rotation,
                )
                annot.set_info(title="Rechnungs-Tinder", content=text)
                annot.update()
                xref = annot.xref
                self._save(doc, name)
                return xref
            finally:
                if not doc.is_closed:
                    doc.close()

    def add_ink(self, name: str, page: int, strokes: list[list[list[float]]]) -> int:
        """Speichert eine Freihand-Zeichnung (Liste von Strichen aus relativen Punkten)."""
        if not strokes or not all(isinstance(s, list) and len(s) >= 1 for s in strokes):
            raise InvoiceError("Die Zeichnung ist leer.")
        with self._lock:
            doc = self._open(name)
            try:
                pg = self._page(doc, page)
                ink = []
                for stroke in strokes:
                    points = [self._to_page_point(pg, p[0], p[1]) for p in stroke]
                    if len(points) == 1:  # einzelner Punkt -> kleiner Strich
                        points.append(points[0] + (0.5, 0.5))
                    ink.append([(p.x, p.y) for p in points])
                annot = pg.add_ink_annot(ink)
                annot.set_colors(stroke=INK_COLOR)
                annot.set_border(width=max(1.5, min(pg.rect.width, pg.rect.height) / 250))
                annot.set_info(title="Rechnungs-Tinder")
                annot.update()
                xref = annot.xref
                self._save(doc, name)
                return xref
            finally:
                if not doc.is_closed:
                    doc.close()

    def delete_annotation(self, name: str, page: int, xref: int) -> None:
        with self._lock:
            doc = self._open(name)
            try:
                pg = self._page(doc, page)
                for annot in pg.annots():
                    if annot.xref == int(xref):
                        pg.delete_annot(annot)
                        self._save(doc, name)
                        return
                raise InvoiceError("Diese Anmerkung gibt es nicht mehr.")
            finally:
                if not doc.is_closed:
                    doc.close()


def _friendly_os_error(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "Keine Berechtigung oder Datei ist in einem anderen Programm geöffnet."
    return str(exc.strerror or exc)
