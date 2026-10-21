import json
import re

import pymupdf
import pytest

from rechnungs_tinder.app import create_app
from rechnungs_tinder.settings import Settings

from test_core import make_pdf

LAN = {"REMOTE_ADDR": "192.168.1.50"}  # Anfrage von einem Smartphone im WLAN


@pytest.fixture
def folder(tmp_path):
    share = tmp_path / "Freigabe"
    invoices = share / "Rechnungen"
    invoices.mkdir(parents=True)
    for name in ["Rechnung 10.pdf", "Rechnung 2.pdf", "Rechnung 1.PDF"]:
        make_pdf(invoices / name)
    (tmp_path / "Geheim").mkdir()
    make_pdf(tmp_path / "Geheim" / "privat.pdf")
    return invoices


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / "einstellungen.json")


def local_token(client):
    html = client.get("/").get_data(as_text=True)
    return re.search(r'window.TOKEN = "([^"]*)"', html).group(1)


@pytest.fixture
def client(settings):
    c = create_app(settings).test_client()
    c.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + local_token(c)
    return c


@pytest.fixture
def net_app(settings, folder):
    return create_app(settings, network=True, shares=[str(folder.parent)], pin="4711")


# ------------------------------------------------------------- lokal


def test_local_index_contains_token(settings):
    c = create_app(settings).test_client()
    assert local_token(c)


def test_api_requires_token(settings):
    c = create_app(settings).test_client()
    res = c.get("/api/v1/durchsuchen", headers={"Authorization": "Bearer falsch"})
    assert res.status_code == 401
    assert res.get_json()["code"] == "anmeldung"


def test_no_token_for_foreign_host_name(settings):
    """DNS-Rebinding: fremder Host-Name bekommt keinen Schlüssel, auch von 127.0.0.1."""
    c = create_app(settings).test_client()
    html = c.get("/", headers={"Host": "evil.example"}).get_data(as_text=True)
    assert 'window.TOKEN = ""' in html


def test_info(client):
    info = client.get("/api/v1/info").get_json()
    assert info["api"] == 1 and info["angemeldet"] is True and info["netzwerk"] is False


def test_full_workflow(client, folder):
    res = client.post("/api/v1/ordner", json={"pfad": str(folder)}).get_json()
    names = [r["name"] for r in res["status"]["rechnungen"]]
    assert names == ["Rechnung 1.PDF", "Rechnung 2.pdf", "Rechnung 10.pdf"]
    assert res["letzte_ordner"] == [str(folder.resolve())]
    o = res["status"]["ordner"]

    info = client.get("/api/v1/rechnung", query_string={"ordner": o, "name": "Rechnung 2.pdf"}).get_json()
    assert len(info["seiten"]) == 1
    img = client.get("/api/v1/seite", query_string={"ordner": o, "name": "Rechnung 2.pdf", "seite": 0, "breite": 300})
    assert img.mimetype == "image/jpeg"
    pdf = client.get("/api/v1/datei", query_string={"ordner": o, "name": "Rechnung 2.pdf"})
    assert pdf.mimetype == "application/pdf" and pdf.data.startswith(b"%PDF")

    note = client.post("/api/v1/notiz", json={"ordner": o, "name": "Rechnung 2.pdf", "seite": 0, "x": 0.2, "y": 0.2, "text": "OK"})
    assert note.status_code == 200 and note.get_json()["version"] != info["version"]

    for name, decision in [("Rechnung 1.PDF", "bewilligt"), ("Rechnung 2.pdf", "abgelehnt"), ("Rechnung 10.pdf", "bewilligt")]:
        client.post("/api/v1/entscheiden", json={"ordner": o, "name": name, "entscheidung": decision})
    assert client.post("/api/v1/rueckgaengig", json={"ordner": o}).get_json()["name"] == "Rechnung 10.pdf"
    client.post("/api/v1/entscheiden", json={"ordner": o, "name": "Rechnung 10.pdf", "entscheidung": "abgelehnt"})

    status = client.get("/api/v1/ordner", query_string={"pfad": o}).get_json()["status"]
    assert all(r["entscheidung"] for r in status["rechnungen"])

    result = client.post("/api/v1/verschieben", json={"ordner": o}).get_json()["ergebnis"]
    assert result["verschoben"] == {"bewilligt": ["Rechnung 1.PDF"], "abgelehnt": ["Rechnung 2.pdf", "Rechnung 10.pdf"]}
    with pymupdf.open(folder / "Abgelehnt" / "Rechnung 2.pdf") as doc:
        assert len(list(doc[0].annots())) == 1


def test_errors_are_german_json(client, folder):
    res = client.post("/api/v1/entscheiden", json={"name": "x.pdf", "entscheidung": "bewilligt"})
    assert res.status_code == 400
    assert "Ordner" in res.get_json()["fehler"]
    res = client.post("/api/v1/ordner", json={"pfad": str(folder / "gibtsnicht")})
    assert "nicht gefunden" in res.get_json()["fehler"]


def test_browse(client, folder):
    (folder / "Unterordner").mkdir()
    res = client.get("/api/v1/durchsuchen", query_string={"pfad": str(folder)}).get_json()
    assert [d["name"] for d in res["ordner"]] == ["Unterordner"]
    assert res["pdfs"] == 3
    roots = client.get("/api/v1/durchsuchen").get_json()
    assert roots["pfad"] is None and roots["ordner"]


def test_manifest(client):
    data = json.loads(client.get("/manifest.webmanifest").data)
    assert data["display"] == "standalone"


# ---------------------------------------------------------- Netzwerk


def test_network_requires_share(settings):
    with pytest.raises(ValueError):
        create_app(settings, network=True, shares=[])


def test_network_index_has_no_token(net_app):
    html = net_app.test_client().get("/", environ_base=LAN).get_data(as_text=True)
    assert 'window.TOKEN = ""' in html


def test_network_login(net_app, folder):
    c = net_app.test_client()
    c.environ_base.update(LAN)
    assert c.get("/api/v1/info").get_json()["angemeldet"] is False
    assert c.get("/api/v1/durchsuchen").status_code == 401

    assert c.post("/api/v1/anmelden", json={"pin": "0000"}).status_code == 401
    token = c.post("/api/v1/anmelden", json={"pin": "4711"}).get_json()["token"]
    c.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + token

    info = c.get("/api/v1/info").get_json()
    assert info["angemeldet"] is True and info["systemdialog"] is False
    assert info["freigaben"] == [str(folder.parent.resolve())]
    res = c.post("/api/v1/ordner", json={"pfad": str(folder)})
    assert res.status_code == 200
    # Bild-URLs (img-Tag) dürfen den Schlüssel als Parameter tragen.
    o = res.get_json()["status"]["ordner"]
    img = net_app.test_client().get(
        "/api/v1/seite", query_string={"ordner": o, "name": "Rechnung 2.pdf", "t": token}, environ_base=LAN
    )
    assert img.status_code == 200


def test_network_pin_change_invalidates_tokens(settings, folder):
    app = create_app(settings, network=True, shares=[str(folder)], pin="1111")
    token = app.test_client().post("/api/v1/anmelden", json={"pin": "1111"}, environ_base=LAN).get_json()["token"]
    app2 = create_app(settings, network=True, shares=[str(folder)], pin="2222")
    res = app2.test_client().get("/api/v1/durchsuchen", headers={"Authorization": "Bearer " + token}, environ_base=LAN)
    assert res.status_code == 401


def test_network_login_rate_limit(net_app):
    c = net_app.test_client()
    c.environ_base.update(LAN)
    for _ in range(5):
        assert c.post("/api/v1/anmelden", json={"pin": "9999"}).status_code == 401
    assert c.post("/api/v1/anmelden", json={"pin": "4711"}).status_code == 429


def test_network_only_shared_folders(net_app, folder):
    c = net_app.test_client()
    c.environ_base.update(LAN)
    token = c.post("/api/v1/anmelden", json={"pin": "4711"}).get_json()["token"]
    c.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + token
    secret = folder.parent.parent / "Geheim"

    assert c.post("/api/v1/ordner", json={"pfad": str(secret)}).status_code == 403
    assert c.get("/api/v1/ordner", query_string={"pfad": str(folder / ".." / ".." / "Geheim")}).status_code == 403
    assert c.get("/api/v1/durchsuchen", query_string={"pfad": str(secret)}).status_code == 403
    assert c.get("/api/v1/seite", query_string={"ordner": str(secret), "name": "privat.pdf"}).status_code == 403

    roots = c.get("/api/v1/durchsuchen").get_json()
    assert [r["pfad"] for r in roots["ordner"]] == [str(folder.parent.resolve())]
    top = c.get("/api/v1/durchsuchen", query_string={"pfad": str(folder.parent)}).get_json()
    assert top["oben"] == ""  # nicht über die Freigabe hinaus


def test_network_no_native_dialog_remote(net_app):
    c = net_app.test_client()
    c.environ_base.update(LAN)
    token = c.post("/api/v1/anmelden", json={"pin": "4711"}).get_json()["token"]
    res = c.post("/api/v1/systemdialog", json={}, headers={"Authorization": "Bearer " + token})
    assert res.status_code == 400


# ---------------------------------------------------------- Einstellungen


def test_settings_remember(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.remember(str(tmp_path))
    assert json.loads((tmp_path / "s.json").read_text())["letzte_ordner"] == [str(tmp_path)]


def test_settings_pin_and_secret_persist(tmp_path):
    s = Settings(tmp_path / "s.json")
    pin = s.pin(create=True)
    secret = s.secret()
    assert len(pin) == 6 and pin.isdigit()
    again = Settings(tmp_path / "s.json")
    assert again.pin() == pin and again.secret() == secret


def test_shares_from_settings_only_restrict_network_mode(settings, folder, tmp_path):
    settings.data["freigaben"] = [str(folder)]
    local = create_app(settings).test_client()
    local.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + local_token(local)
    assert local.post("/api/v1/ordner", json={"pfad": str(tmp_path / "Geheim")}).status_code == 200

    net = create_app(settings, network=True, pin="1").test_client()
    net.environ_base.update(LAN)
    token = net.post("/api/v1/anmelden", json={"pin": "1"}).get_json()["token"]
    res = net.post("/api/v1/ordner", json={"pfad": str(tmp_path / "Geheim")}, headers={"Authorization": "Bearer " + token})
    assert res.status_code == 403
