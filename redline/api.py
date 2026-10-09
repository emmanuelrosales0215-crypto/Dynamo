"""HTTP API: upload a drawing set, add and review markups, download the PDF."""
from __future__ import annotations

import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Literal

import pymupdf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import markups

STATIC = Path(__file__).parent / "static"
WORKDIR = Path(os.environ.get("REDLINE_DATA", Path(tempfile.gettempdir()) / "redline"))
app = FastAPI(title="Redline")


def _path(doc_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", doc_id):
        raise HTTPException(404, "unknown document")
    p = WORKDIR / f"{doc_id}.pdf"
    if not p.exists():
        raise HTTPException(404, "unknown document")
    return p


def _open(doc_id: str) -> tuple[pymupdf.Document, Path]:
    p = _path(doc_id)
    return pymupdf.open(p), p


def _save(doc: pymupdf.Document, p: Path) -> None:
    tmp = p.with_suffix(".tmp")
    doc.save(tmp, deflate=True)
    doc.close()
    os.replace(tmp, p)


class NewMarkup(BaseModel):
    type: Literal["cloud", "text", "stamp"]
    page: int = Field(ge=0)
    rect: tuple[float, float, float, float]
    text: str = ""
    author: str = ""
    color: tuple[float, float, float] = (1.0, 0.0, 0.0)


class MarkupEdit(BaseModel):
    rect: tuple[float, float, float, float] | None = None
    text: str | None = None
    color: tuple[float, float, float] | None = None


class StatusChange(BaseModel):
    status: Literal["Accepted", "Rejected", "Canceled", "Completed", "None"]
    author: str = ""


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.post("/documents")
async def upload(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    try:
        pymupdf.open(stream=data, filetype="pdf").close()
    except Exception:
        raise HTTPException(400, "not a readable PDF")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4().hex
    (WORKDIR / f"{doc_id}.pdf").write_bytes(data)
    return {"id": doc_id}


@app.get("/documents/{doc_id}/info")
def info(doc_id: str) -> dict:
    doc, _ = _open(doc_id)
    try:
        return {"pages": [{"width": p.rect.width, "height": p.rect.height} for p in doc]}
    finally:
        doc.close()


@app.get("/documents/{doc_id}/markups")
def get_markups(doc_id: str) -> list[dict]:
    doc, _ = _open(doc_id)
    try:
        return [m.as_dict() for m in markups.list_markups(doc)]
    finally:
        doc.close()


@app.post("/documents/{doc_id}/markups")
def create_markup(doc_id: str, body: NewMarkup) -> dict:
    doc, p = _open(doc_id)
    if body.page >= len(doc):
        doc.close()
        raise HTTPException(400, "page out of range")
    page = doc[body.page]
    fn = {"cloud": markups.add_cloud, "text": markups.add_text,
          "stamp": markups.add_stamp}[body.type]
    annot = fn(page, body.rect, body.text, body.author, body.color)
    xref = annot.xref
    _save(doc, p)
    return {"page": body.page, "xref": xref}


def _edit(doc_id: str, page: int, work) -> dict:
    doc, p = _open(doc_id)
    try:
        if not 0 <= page < len(doc):
            raise HTTPException(400, "page out of range")
        result = work(doc)
    except KeyError as e:
        doc.close()
        raise HTTPException(404, str(e))
    except HTTPException:
        doc.close()
        raise
    _save(doc, p)
    return result


@app.patch("/documents/{doc_id}/markups/{page}/{xref}")
def edit_markup(doc_id: str, page: int, xref: int, body: MarkupEdit) -> dict:
    return _edit(doc_id, page, lambda doc: {"page": page, "xref": markups.update_markup(
        doc, page, xref, rect=body.rect, text=body.text, color=body.color)})


@app.delete("/documents/{doc_id}/markups/{page}/{xref}")
def remove_markup(doc_id: str, page: int, xref: int) -> dict:
    return _edit(doc_id, page, lambda doc: markups.delete_markup(doc, page, xref) or {"deleted": xref})


@app.post("/documents/{doc_id}/markups/{page}/{xref}/status")
def change_status(doc_id: str, page: int, xref: int, body: StatusChange) -> dict:
    doc, p = _open(doc_id)
    try:
        if not 0 <= page < len(doc):
            raise HTTPException(400, "page out of range")
        markups.set_status(doc, page, xref, body.status, body.author)
    except KeyError as e:
        doc.close()
        raise HTTPException(404, str(e))
    except HTTPException:
        doc.close()
        raise
    _save(doc, p)
    return {"status": body.status}


@app.get("/documents/{doc_id}/pages/{page}.png")
def render_page(doc_id: str, page: int, dpi: int = 100) -> Response:
    doc, _ = _open(doc_id)
    try:
        if not 0 <= page < len(doc):
            raise HTTPException(404, "page out of range")
        png = doc[page].get_pixmap(dpi=min(max(dpi, 36), 300)).tobytes("png")
    finally:
        doc.close()
    return Response(png, media_type="image/png")


@app.get("/documents/{doc_id}/file")
def download(doc_id: str) -> FileResponse:
    return FileResponse(_path(doc_id), media_type="application/pdf",
                        filename=f"{doc_id}.pdf")
