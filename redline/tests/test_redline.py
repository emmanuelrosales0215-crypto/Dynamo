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


def test_update_and_delete(doc):
    cloud = markups.add_cloud(doc[0], (100, 100, 200, 160), "a", "Eng").xref
    markups.set_status(doc, 0, cloud, "Completed")
    text = markups.add_text(doc[0], (300, 100, 500, 140), "hello", "Eng").xref
    cloud = markups.update_markup(doc, 0, cloud, rect=(150, 150, 300, 260), text="b", color=(0, 0, 1))
    assert markups.update_markup(doc, 0, text, rect=(310, 110, 520, 160), text="bye") == text
    got = {m.xref: m for m in markups.list_markups(doc)}
    assert got[cloud].rect == (150, 150, 300, 260) and got[cloud].content == "b"
    assert tuple(got[cloud].color) == (0.0, 0.0, 1.0) and got[cloud].status == "Completed"
    assert got[text].content == "bye" and "bye" in doc[0].get_text()
    markups.delete_markup(doc, 0, cloud)
    left = markups.list_markups(doc)
    assert [m.xref for m in left] == [text]
    assert len(list(doc[0].annots())) == 1  # status reply removed too
    with pytest.raises(KeyError):
        markups.delete_markup(doc, 0, cloud)


def test_api_edit_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    c = TestClient(api.app)
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}).json()["id"]
    xref = c.post(f"/documents/{doc_id}/markups", json={
        "type": "cloud", "page": 0, "rect": [100, 100, 200, 160], "text": "a"}).json()["xref"]
    r = c.patch(f"/documents/{doc_id}/markups/0/{xref}", json={"rect": [10, 10, 90, 70], "text": "b"})
    assert r.status_code == 200
    ms = c.get(f"/documents/{doc_id}/markups").json()
    assert ms[0]["content"] == "b" and ms[0]["rect"] == [10, 10, 90, 70]
    assert c.patch(f"/documents/{doc_id}/markups/0/9999", json={"text": "x"}).status_code == 404
    assert c.patch(f"/documents/{doc_id}/markups/7/{xref}", json={"text": "x"}).status_code == 400
    assert c.delete(f"/documents/{doc_id}/markups/0/{ms[0]['xref']}").status_code == 200
    assert c.get(f"/documents/{doc_id}/markups").json() == []
    assert c.delete(f"/documents/{doc_id}/markups/0/{xref}").status_code == 404


def test_undo_redo(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    c = TestClient(api.app)
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}).json()["id"]
    assert c.post(f"/documents/{doc_id}/undo").status_code == 409
    xref = c.post(f"/documents/{doc_id}/markups", json={
        "type": "text", "page": 0, "rect": [10, 10, 200, 40], "text": "one"}).json()["xref"]
    c.patch(f"/documents/{doc_id}/markups/0/{xref}", json={"text": "two"})
    c.delete(f"/documents/{doc_id}/markups/0/{xref}")
    count = lambda: len(c.get(f"/documents/{doc_id}/markups").json())
    text = lambda: c.get(f"/documents/{doc_id}/markups").json()[0]["content"]
    assert count() == 0 and c.get(f"/documents/{doc_id}/info").json()["can_undo"]
    assert c.post(f"/documents/{doc_id}/undo").json() == {"can_undo": True, "can_redo": True}
    assert text() == "two"
    c.post(f"/documents/{doc_id}/undo")
    assert text() == "one"
    c.post(f"/documents/{doc_id}/redo")
    assert text() == "two"
    # a new edit clears redo
    c.patch(f"/documents/{doc_id}/markups/0/{xref}", json={"text": "three"})
    assert not c.get(f"/documents/{doc_id}/info").json()["can_redo"]
    assert c.post(f"/documents/{doc_id}/redo").status_code == 409
    for _ in range(3):
        c.post(f"/documents/{doc_id}/undo")
    assert count() == 0
    assert c.post(f"/documents/{doc_id}/undo").status_code == 409


def test_undo_history_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKDIR", tmp_path)
    monkeypatch.setattr(api, "MAX_UNDO", 3)
    c = TestClient(api.app)
    doc_id = c.post("/documents", files={"file": ("a.pdf", make_pdf(), "application/pdf")}).json()["id"]
    for i in range(6):
        c.post(f"/documents/{doc_id}/markups", json={"type": "text", "page": 0, "rect": [10, 10, 99, 40], "text": str(i)})
    assert len(list((tmp_path / f"{doc_id}.undo").glob("*.pdf"))) == 3
