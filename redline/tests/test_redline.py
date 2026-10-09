import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from redline import api, markups
from redline.studio import StudioClient, StudioConfig, StudioError


def make_pdf(pages=2) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=792, height=612)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def doc():
    d = pymupdf.open(stream=make_pdf(), filetype="pdf")
    yield d
    d.close()


def test_markups_roundtrip(doc):
    markups.add_cloud(doc[0], (100, 100, 200, 160), "Move storm line", "Eng")
    markups.add_text(doc[1], (50, 50, 250, 90), "Verify invert", "Eng")
    markups.add_stamp(doc[1], (300, 300, 500, 340), "Revised", "Eng")
    reopened = pymupdf.open(stream=doc.tobytes(), filetype="pdf")
    found = markups.list_markups(reopened)
    assert {m.subject for m in found} == {"Cloud", "Text Box", "Stamp"}
    cloud = next(m for m in found if m.subject == "Cloud")
    assert cloud.content == "Move storm line" and cloud.author == "Eng"
    assert "/S/C" in reopened.xref_object(cloud.xref).replace(" ", "")


def test_status_is_hidden_irt_reply(doc):
    a = markups.add_cloud(doc[0], (10, 10, 60, 40), "x", "Eng")
    reply = markups.set_status(doc, 0, a.xref, "Completed", "Rev")
    obj = doc.xref_object(reply)
    assert "/IRT" in obj and "/StateModel(Review)" in obj.replace(" ", "")
    found = markups.list_markups(doc)
    assert len(found) == 1 and found[0].status == "Completed"
    markups.set_status(doc, 0, a.xref, "Rejected")
    assert markups.list_markups(doc)[0].status == "Rejected"


def test_bad_status(doc):
    a = markups.add_cloud(doc[0], (10, 10, 60, 40))
    with pytest.raises(ValueError):
        markups.set_status(doc, 0, a.xref, "Done")


def test_api_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    c = TestClient(api.app)
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}).json()["id"]
    r = c.post(f"/documents/{doc_id}/markups", json={
        "type": "cloud", "page": 0, "rect": [100, 100, 200, 160], "text": "Check", "author": "Eng"})
    assert r.status_code == 200
    xref = r.json()["xref"]
    r = c.post(f"/documents/{doc_id}/markups/0/{xref}/status", json={"status": "Accepted"})
    assert r.status_code == 200
    ms = c.get(f"/documents/{doc_id}/markups").json()
    assert len(ms) == 1 and ms[0]["status"] == "Accepted"
    assert c.get(f"/documents/{doc_id}/pages/0.png").content[:4] == b"\x89PNG"
    assert c.get(f"/documents/{doc_id}/file").content[:4] == b"%PDF"


def test_api_rejects_bad_input(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    c = TestClient(api.app)
    assert c.post("/documents", files={"file": ("a.pdf", b"nope", "application/pdf")}).status_code == 400
    assert c.get("/documents/../etc/markups").status_code == 404
    assert c.get("/documents/" + "0" * 32 + "/markups").status_code == 404
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(1), "application/pdf")}).json()["id"]
    r = c.post(f"/documents/{doc_id}/markups", json={"type": "cloud", "page": 5, "rect": [0, 0, 9, 9]})
    assert r.status_code == 400


def test_studio_client():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"Sessions": []})
    cfg = StudioConfig("id", "secret", "http://localhost/cb")
    s = StudioClient(cfg, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(StudioError):
        s.list_sessions()
    assert "client_id=id" in s.authorize_url("st")
    s.exchange_code("code")
    assert s.list_sessions() == {"Sessions": []}


def test_viewer_and_info(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    c = TestClient(api.app)
    r = c.get("/")
    assert r.status_code == 200 and "<title>Redline</title>" in r.text
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(2), "application/pdf")}).json()["id"]
    pages = c.get(f"/documents/{doc_id}/info").json()["pages"]
    assert len(pages) == 2 and pages[0] == {"width": 792, "height": 612}
