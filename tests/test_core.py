import json

import pymupdf
import pytest

from rechnungs_tinder.app import create_app
from rechnungs_tinder.core import STATE_FILE, InvoiceError, InvoiceFolder
from rechnungs_tinder.settings import Settings


def make_pdf(path, text="Rechnung", pages=1, rotate=0):
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Seite {i + 1}")
        page.set_rotation(rotate)
    doc.save(path)
    doc.close()


@pytest.fixture
def folder(tmp_path):
    for name in ["Rechnung 10.pdf", "Rechnung 2.pdf", "Rechnung 1.PDF"]:
        make_pdf(tmp_path / name)
    (tmp_path / "notiz.txt").write_text("keine Rechnung")
    return tmp_path


def test_lists_pdfs_naturally_sorted(folder):
    f = InvoiceFolder(folder)
    assert f.invoices() == ["Rechnung 1.PDF", "Rechnung 2.pdf", "Rechnung 10.pdf"]


def test_rejects_path_traversal(folder):
    f = InvoiceFolder(folder)
    for bad in ["../x.pdf", "sub/x.pdf", ".rechnungs-tinder.json", ""]:
        with pytest.raises(InvoiceError):
            f.path_of(bad)


def test_decisions_persist_and_undo(folder):
    f = InvoiceFolder(folder)
    f.decide("Rechnung 1.PDF", "bewilligt")
    f.decide("Rechnung 2.pdf", "abgelehnt")
    assert (folder / STATE_FILE).exists()

    reopened = InvoiceFolder(folder)
    assert reopened.decisions == {"Rechnung 1.PDF": "bewilligt", "Rechnung 2.pdf": "abgelehnt"}
    assert reopened.undo() == "Rechnung 2.pdf"
    assert reopened.undo() == "Rechnung 1.PDF"
    assert reopened.undo() is None
    assert not (folder / STATE_FILE).exists()


def test_move_into_target_folders(folder):
    (folder / "Bewilligt").mkdir()
    make_pdf(folder / "Bewilligt" / "Rechnung 1.PDF")  # Namenskonflikt
    f = InvoiceFolder(folder)
    f.decide("Rechnung 1.PDF", "bewilligt")
    f.decide("Rechnung 2.pdf", "abgelehnt")
    f.decide("Rechnung 10.pdf", "bewilligt")

    result = f.move_decided()

    assert result["fehler"] == []
    assert sorted(result["verschoben"]["bewilligt"]) == ["Rechnung 1 (2).PDF", "Rechnung 10.pdf"]
    assert result["verschoben"]["abgelehnt"] == ["Rechnung 2.pdf"]
    assert (folder / "Abgelehnt" / "Rechnung 2.pdf").is_file()
    assert (folder / "Bewilligt" / "Rechnung 1 (2).PDF").is_file()
    assert f.invoices() == []
    assert not (folder / STATE_FILE).exists()


def test_custom_absolute_target(folder, tmp_path_factory):
    target = tmp_path_factory.mktemp("ok")
    f = InvoiceFolder(folder, {"bewilligt": str(target)})
    f.decide("Rechnung 2.pdf", "bewilligt")
    f.move_decided()
    assert (target / "Rechnung 2.pdf").is_file()


def test_note_and_ink_are_written_into_pdf(folder):
    f = InvoiceFolder(folder)
    name = "Rechnung 2.pdf"
    note = f.add_note(name, 0, 0.5, 0.5, "Betrag prüfen: 12,50 € – Größe ä ö ü ß")
    ink = f.add_ink(name, 0, [[[0.1, 0.1], [0.2, 0.2], [0.3, 0.1]]])

    with pymupdf.open(folder / name) as doc:
        page = doc[0]
        annots = {a.xref: (a.type[1], a.info["content"], a.rect) for a in page.annots()}
        assert annots[note][0] == "FreeText"
        assert "Größe ä ö ü ß" in annots[note][1]
        assert annots[ink][0] == "Ink"
        # Notiz liegt dort, wo getippt wurde (Seitenmitte).
        assert annots[note][2].x0 == pytest.approx(page.rect.width / 2, abs=1)
        assert annots[note][2].y0 == pytest.approx(page.rect.height / 2, abs=1)

    f.delete_annotation(name, 0, note)
    with pymupdf.open(folder / name) as doc:
        assert [a.xref for a in doc[0].annots()] == [ink]


def test_note_on_rotated_page_appears_where_tapped(tmp_path):
    make_pdf(tmp_path / "quer.pdf", rotate=90)
    f = InvoiceFolder(tmp_path)
    f.add_note("quer.pdf", 0, 0.05, 0.05, "Hier")  # oben links in der Anzeige
    with pymupdf.open(tmp_path / "quer.pdf") as doc:
        page = doc[0]
        annot = next(page.annots())
        shown = annot.rect * page.rotation_matrix
        assert shown.x0 < page.rect.width * 0.2
        assert shown.y0 < page.rect.height * 0.2


def test_note_near_edge_stays_on_page(folder):
    f = InvoiceFolder(folder)
    xref = f.add_note("Rechnung 2.pdf", 0, 1.0, 1.0, "Ganz unten rechts mit etwas längerem Text")
    with pymupdf.open(folder / "Rechnung 2.pdf") as doc:
        page = doc[0]
        annot = next(a for a in page.annots() if a.xref == xref)
        assert (page.rect + (-1, -1, 1, 1)).contains(annot.rect)


def test_render_returns_jpeg(folder):
    data = InvoiceFolder(folder).render("Rechnung 2.pdf", 0, 400)
    assert data[:2] == b"\xff\xd8"


# ------------------------------------------------------------------ Web-API


@pytest.fixture
def client(folder, tmp_path_factory):
    settings = Settings(tmp_path_factory.mktemp("cfg") / "einstellungen.json")
    app = create_app(settings, token="geheim")
    c = app.test_client()
    c.environ_base["HTTP_X_TOKEN"] = "geheim"
    return c


def test_api_requires_token(client):
    assert client.get("/api/status", headers={"X-Token": "falsch"}).status_code == 403


def test_api_rejects_foreign_host(client):
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403


def test_index_contains_token(client):
    assert b"geheim" in client.get("/").data


def test_api_full_workflow(client, folder):
    res = client.post("/api/ordner", json={"pfad": str(folder)}).get_json()
    names = [r["name"] for r in res["status"]["rechnungen"]]
    assert names == ["Rechnung 1.PDF", "Rechnung 2.pdf", "Rechnung 10.pdf"]
    assert res["letzte_ordner"] == [str(folder.resolve())]

    info = client.get("/api/rechnung", query_string={"name": "Rechnung 2.pdf"}).get_json()
    assert len(info["seiten"]) == 1
    img = client.get("/api/seite", query_string={"name": "Rechnung 2.pdf", "seite": 0, "breite": 300, "t": "geheim"})
    assert img.mimetype == "image/jpeg"

    note = client.post("/api/notiz", json={"name": "Rechnung 2.pdf", "seite": 0, "x": 0.2, "y": 0.2, "text": "OK"})
    assert note.status_code == 200 and note.get_json()["version"] != info["version"]

    for name, decision in [("Rechnung 1.PDF", "bewilligt"), ("Rechnung 2.pdf", "abgelehnt"), ("Rechnung 10.pdf", "bewilligt")]:
        client.post("/api/entscheiden", json={"name": name, "entscheidung": decision})
    assert client.post("/api/rueckgaengig", json={}).get_json()["name"] == "Rechnung 10.pdf"
    client.post("/api/entscheiden", json={"name": "Rechnung 10.pdf", "entscheidung": "abgelehnt"})

    result = client.post("/api/verschieben", json={}).get_json()["ergebnis"]
    assert result["verschoben"] == {"bewilligt": ["Rechnung 1.PDF"], "abgelehnt": ["Rechnung 2.pdf", "Rechnung 10.pdf"]}
    with pymupdf.open(folder / "Abgelehnt" / "Rechnung 2.pdf") as doc:
        assert len(list(doc[0].annots())) == 1


def test_api_errors_are_german_json(client, folder):
    res = client.post("/api/entscheiden", json={"name": "x.pdf", "entscheidung": "bewilligt"})
    assert res.status_code == 400
    assert "Ordner" in res.get_json()["fehler"]
    res = client.post("/api/ordner", json={"pfad": str(folder / "gibtsnicht")})
    assert "nicht gefunden" in res.get_json()["fehler"]


def test_browse(client, folder):
    (folder / "Unterordner").mkdir()
    res = client.get("/api/durchsuchen", query_string={"pfad": str(folder)}).get_json()
    assert [d["name"] for d in res["ordner"]] == ["Unterordner"]
    assert res["pdfs"] == 3
    roots = client.get("/api/durchsuchen").get_json()
    assert roots["pfad"] is None and roots["ordner"]


def test_settings_remember(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.remember(str(tmp_path))
    assert json.loads((tmp_path / "s.json").read_text())["letzte_ordner"] == [str(tmp_path)]
