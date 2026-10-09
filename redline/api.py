"""HTTP API: sign in, upload drawings, share them, add/review markups, per-user undo."""
from __future__ import annotations

import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import urlparse

import pymupdf
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import auth, history, markups, review
from .db import connect, data_dir

STATIC = Path(__file__).parent / "static"
MAX_UPLOAD = int(float(os.environ.get("REDLINE_MAX_UPLOAD_MB", "100")) * 1024 * 1024)

app = FastAPI(title="Redline")
app.include_router(auth.router)


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    """Refuse state-changing requests that come from another site's page."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
    return await call_next(request)


# ---- documents and access

DOC_ID = re.compile(r"[0-9a-f]{32}")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
User = dict


def _lock(doc_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(doc_id, threading.Lock())


def _pdf(doc_id: str) -> Path:
    return data_dir() / "docs" / f"{doc_id}.pdf"


def _access(doc_id: str, user: User) -> dict:
    """The document row plus the caller's role; 404 for strangers so ids don't leak."""
    if not DOC_ID.fullmatch(doc_id):
        raise HTTPException(404, "unknown document")
    with connect() as c:
        row = c.execute(
            "SELECT d.id, d.name, d.owner_id, o.username AS owner, d.created, "
            "EXISTS(SELECT 1 FROM members m WHERE m.doc_id=d.id AND m.user_id=?) AS member "
            "FROM documents d JOIN users o ON o.id=d.owner_id WHERE d.id=?",
            (user["id"], doc_id)).fetchone()
    if not row or not (row["owner_id"] == user["id"] or row["member"]):
        raise HTTPException(404, "unknown document")
    out = dict(row)
    out["role"] = "owner" if row["owner_id"] == user["id"] else "member"
    return out


def _owner_only(doc_id: str, user: User) -> dict:
    doc = _access(doc_id, user)
    if doc["role"] != "owner":
        raise HTTPException(403, "only the owner can do that")
    return doc


def _log(doc_id: str, user: User, summary: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO activity(doc_id,user_id,summary) VALUES(?,?,?)",
                  (doc_id, user["id"], summary))


def _save(doc: pymupdf.Document, path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    doc.save(tmp, deflate=True)
    doc.close()
    os.replace(tmp, path)


def _mutate(doc_id: str, user: User, work: Callable[[pymupdf.Document], tuple[dict, dict | None, str]]) -> dict:
    """Run an edit under the document lock, save it, and record it for this user.

    ``work`` returns (response, undo operation or None, activity summary).
    """
    _access(doc_id, user)
    with _lock(doc_id):
        doc = pymupdf.open(_pdf(doc_id))
        try:
            result, op, summary = work(doc)
        except KeyError as e:
            doc.close()
            raise HTTPException(404, str(e).strip("'\""))
        except ValueError as e:
            doc.close()
            raise HTTPException(400, str(e))
        except Exception:
            doc.close()
            raise
        _save(doc, _pdf(doc_id))
        if op is not None:
            history.record(doc_id, user["id"], {**op, "summary": summary})
        _log(doc_id, user, summary)
    return result


def _page_check(doc: pymupdf.Document, page: int) -> None:
    if not 0 <= page < len(doc):
        raise HTTPException(400, "page out of range")


# ---- models

class NewMarkup(BaseModel):
    type: Literal["cloud", "text", "stamp"]
    page: int = Field(ge=0)
    rect: tuple[float, float, float, float]
    text: str = Field(default="", max_length=500)
    color: tuple[float, float, float] = (1.0, 0.0, 0.0)


class MarkupEdit(BaseModel):
    rect: tuple[float, float, float, float] | None = None
    text: str | None = Field(default=None, max_length=500)
    color: tuple[float, float, float] | None = None


class StatusChange(BaseModel):
    status: Literal["Accepted", "Rejected", "Canceled", "Completed", "None"]


class ReviewRequest(BaseModel):
    page: int = Field(ge=0)


class ShareWith(BaseModel):
    username: str


# ---- pages

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


# ---- documents

@app.get("/documents")
def list_documents(user: User = Depends(auth.current_user)) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT d.id, d.name, o.username AS owner, d.created, d.owner_id=? AS mine "
            "FROM documents d JOIN users o ON o.id=d.owner_id "
            "WHERE d.owner_id=? OR d.id IN (SELECT doc_id FROM members WHERE user_id=?) "
            "ORDER BY d.created DESC", (user["id"],) * 3).fetchall()
    return [{"id": r["id"], "name": r["name"], "owner": r["owner"], "created": r["created"],
             "role": "owner" if r["mine"] else "member"} for r in rows]


@app.post("/documents")
async def upload(file: UploadFile = File(...), user: User = Depends(auth.current_user)) -> dict:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(400, "not a readable PDF")
    if doc.needs_pass or not doc.page_count:
        doc.close()
        raise HTTPException(400, "PDF is encrypted or has no pages")
    doc_id = uuid.uuid4().hex
    markups.ensure_ids(doc)
    doc.save(_pdf(doc_id), deflate=True)
    doc.close()
    name = (Path(file.filename or "").name or "drawing.pdf")[:120]
    with connect() as c:
        c.execute("INSERT INTO documents(id, owner_id, name) VALUES(?,?,?)", (doc_id, user["id"], name))
    _log(doc_id, user, f"uploaded {name}")
    return {"id": doc_id, "name": name}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str, user: User = Depends(auth.current_user)) -> dict:
    _owner_only(doc_id, user)
    with _lock(doc_id):
        with connect() as c:
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        _pdf(doc_id).unlink(missing_ok=True)
    return {"deleted": doc_id}


@app.get("/documents/{doc_id}/info")
def info(doc_id: str, user: User = Depends(auth.current_user)) -> dict:
    d = _access(doc_id, user)
    with connect() as c:
        members = [r["username"] for r in c.execute(
            "SELECT u.username FROM members m JOIN users u ON u.id=m.user_id WHERE m.doc_id=? "
            "ORDER BY u.username", (doc_id,))]
    doc = pymupdf.open(_pdf(doc_id))
    try:
        pages = [{"width": p.rect.width, "height": p.rect.height} for p in doc]
    finally:
        doc.close()
    return {"name": d["name"], "owner": d["owner"], "role": d["role"], "members": members,
            "pages": pages, **history.available(doc_id, user["id"])}


@app.post("/documents/{doc_id}/share")
def share(doc_id: str, body: ShareWith, user: User = Depends(auth.current_user)) -> dict:
    _owner_only(doc_id, user)
    other = auth.user_by_name(body.username)
    if not other:
        raise HTTPException(404, "no such user")
    if other["id"] == user["id"]:
        raise HTTPException(400, "you already own this document")
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO members(doc_id, user_id) VALUES(?,?)", (doc_id, other["id"]))
    _log(doc_id, user, f"shared with {other['username']}")
    return {"shared_with": other["username"]}


@app.delete("/documents/{doc_id}/share/{username}")
def unshare(doc_id: str, username: str, user: User = Depends(auth.current_user)) -> dict:
    _owner_only(doc_id, user)
    other = auth.user_by_name(username)
    if not other:
        raise HTTPException(404, "no such user")
    with connect() as c:
        c.execute("DELETE FROM members WHERE doc_id=? AND user_id=?", (doc_id, other["id"]))
        c.execute("DELETE FROM history WHERE doc_id=? AND user_id=?", (doc_id, other["id"]))
    _log(doc_id, user, f"stopped sharing with {other['username']}")
    return {"unshared": other["username"]}


@app.get("/documents/{doc_id}/activity")
def activity(doc_id: str, limit: int = 50, user: User = Depends(auth.current_user)) -> list[dict]:
    _access(doc_id, user)
    with connect() as c:
        rows = c.execute(
            "SELECT u.username, a.summary, a.at FROM activity a JOIN users u ON u.id=a.user_id "
            "WHERE a.doc_id=? ORDER BY a.id DESC LIMIT ?", (doc_id, min(max(limit, 1), 200))).fetchall()
    return [{"user": r["username"], "summary": r["summary"], "at": r["at"]} for r in rows]


# ---- markups

@app.get("/documents/{doc_id}/markups")
def get_markups(doc_id: str, user: User = Depends(auth.current_user)) -> list[dict]:
    _access(doc_id, user)
    doc = pymupdf.open(_pdf(doc_id))
    try:
        return [m.as_dict() for m in markups.list_markups(doc)]
    finally:
        doc.close()


@app.post("/documents/{doc_id}/markups")
def create_markup(doc_id: str, body: NewMarkup, user: User = Depends(auth.current_user)) -> dict:
    fn = {"cloud": markups.add_cloud, "text": markups.add_text, "stamp": markups.add_stamp}[body.type]

    def work(doc):
        _page_check(doc, body.page)
        annot = fn(doc[body.page], body.rect, body.text, user["username"], body.color)
        snap = markups.snapshot(doc, markups.get_id(doc, annot.xref))
        return ({"id": snap["id"], "page": body.page}, {"t": "create", "snap": snap},
                f"added a {snap['subject'].lower()} on sheet {body.page + 1}")
    return _mutate(doc_id, user, work)


@app.patch("/documents/{doc_id}/markups/{markup_id}")
def edit_markup(doc_id: str, markup_id: str, body: MarkupEdit,
                user: User = Depends(auth.current_user)) -> dict:
    def work(doc):
        page, xref = markups.find(doc, markup_id)
        before = markups.snapshot(doc, markup_id)
        markups.update_markup(doc, page, xref, rect=body.rect, text=body.text, color=body.color)
        after = markups.snapshot(doc, markup_id)
        asked = {k for k in ("rect", "text", "color") if getattr(body, k) is not None}
        result = {"id": markup_id, "page": after["page"]}
        if body.text is not None and after["type"] == "FreeText" and \
                markups.text_overflows(doc, markups.find(doc, markup_id)[1], body.text):
            result["warning"] = ("The text is longer than the box and may be cut off in the drawing. "
                                 "Boxes made in other programs can't be resized here.")
        return (result, history.edit_op(before, after, asked),
                f"edited a {after['subject'].lower()} on sheet {after['page'] + 1}")
    return _mutate(doc_id, user, work)


@app.delete("/documents/{doc_id}/markups/{markup_id}")
def remove_markup(doc_id: str, markup_id: str, user: User = Depends(auth.current_user)) -> dict:
    def work(doc):
        page, xref = markups.find(doc, markup_id)
        snap = markups.snapshot(doc, markup_id)
        markups.delete_markup(doc, page, xref)
        op = {"t": "delete", "snap": snap} if snap["restorable"] else None
        return ({"deleted": markup_id, "undoable": op is not None}, op,
                f"deleted a {snap['subject'].lower()} on sheet {snap['page'] + 1}")
    return _mutate(doc_id, user, work)


@app.post("/documents/{doc_id}/markups/{markup_id}/status")
def change_status(doc_id: str, markup_id: str, body: StatusChange,
                  user: User = Depends(auth.current_user)) -> dict:
    def work(doc):
        page, xref = markups.find(doc, markup_id)
        before = markups.snapshot(doc, markup_id)
        markups.set_status(doc, page, xref, body.status, user["username"])
        op = {"t": "status", "id": markup_id, "before": before["status"], "after": body.status}
        return ({"id": markup_id, "status": body.status}, op,
                f"set a {before['subject'].lower()} to {body.status}")
    return _mutate(doc_id, user, work)


# ---- per-user undo / redo

def _step(doc_id: str, user: User, undo: bool) -> dict:
    _access(doc_id, user)
    src, dst = ("undo", "redo") if undo else ("redo", "undo")
    with _lock(doc_id):
        entry = history.peek(doc_id, user["id"], src)
        if entry is None:
            raise HTTPException(409, f"nothing to {src}")
        entry_id, op = entry
        doc = pymupdf.open(_pdf(doc_id))
        try:
            history.run(doc, op, undo)
        except history.Conflict as e:
            doc.close()
            history.move(doc_id, user["id"], entry_id, None)
            raise HTTPException(409, f"Can't {src} that step: {e}. It was dropped.")
        except Exception:
            doc.close()
            raise
        _save(doc, _pdf(doc_id))
        history.move(doc_id, user["id"], entry_id, dst)
        _log(doc_id, user, f"{'undid' if undo else 'redid'}: {op.get('summary', op['t'])}")
    return history.available(doc_id, user["id"])


@app.post("/documents/{doc_id}/undo")
def undo(doc_id: str, user: User = Depends(auth.current_user)) -> dict:
    return _step(doc_id, user, True)


@app.post("/documents/{doc_id}/redo")
def redo(doc_id: str, user: User = Depends(auth.current_user)) -> dict:
    return _step(doc_id, user, False)


# ---- AI review assistant

@app.get("/ai/status")
def ai_status(user: User = Depends(auth.current_user)) -> dict:
    limit = review.daily_limit()
    return {"enabled": review.enabled(), "limit": limit, "remaining": max(limit - review.used_today(user["id"]), 0)}


@app.post("/documents/{doc_id}/review")
def ai_review(doc_id: str, body: ReviewRequest, user: User = Depends(auth.current_user)) -> dict:
    d = _access(doc_id, user)
    if not review.enabled():
        raise HTTPException(503, "AI review isn't set up on this server (no ANTHROPIC_API_KEY).")
    doc = pymupdf.open(_pdf(doc_id))
    try:
        _page_check(doc, body.page)
        png = review.render_sheet(doc, body.page)
        size = (doc[body.page].rect.width, doc[body.page].rect.height)
        pages = len(doc)
        on_sheet = [m.as_dict() for m in markups.list_markups(doc) if m.page == body.page]
    finally:
        doc.close()
    if not review.claim(user["id"]):
        raise HTTPException(429, f"Daily AI review limit reached ({review.daily_limit()}). Try again tomorrow.")
    try:
        result = review.review_sheet(png, d["name"], body.page, pages, size, on_sheet)
    except review.ReviewError as e:
        review.refund(user["id"])
        raise HTTPException(502, str(e))
    except Exception as e:  # SDK errors: don't leak details, don't charge the user's quota
        review.refund(user["id"])
        import logging
        logging.getLogger("redline").warning("AI review failed: %s: %s", type(e).__name__, e)
        status = 503 if type(e).__name__ in ("RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError") else 502
        raise HTTPException(status, "The AI service couldn't complete the review. Please try again shortly.")
    _log(doc_id, user, f"ran an AI review of sheet {body.page + 1}")
    limit = review.daily_limit()
    return {**result, "page": body.page, "remaining": max(limit - review.used_today(user["id"]), 0)}


# ---- rendering and download

@app.get("/documents/{doc_id}/pages/{page}.png")
def render_page(doc_id: str, page: int, dpi: int = 100, user: User = Depends(auth.current_user)) -> Response:
    _access(doc_id, user)
    doc = pymupdf.open(_pdf(doc_id))
    try:
        if not 0 <= page < len(doc):
            raise HTTPException(404, "page out of range")
        png = doc[page].get_pixmap(dpi=min(max(dpi, 36), 300)).tobytes("png")
    finally:
        doc.close()
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})


@app.get("/documents/{doc_id}/file")
def download(doc_id: str, user: User = Depends(auth.current_user)) -> FileResponse:
    d = _access(doc_id, user)
    name = d["name"] if d["name"].lower().endswith(".pdf") else d["name"] + ".pdf"
    return FileResponse(_pdf(doc_id), media_type="application/pdf", filename=name,
                        headers={"Cache-Control": "private, no-store"})
