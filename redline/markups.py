"""Read and write markups on drawing PDFs as standard PDF annotations.

Bluebeam Revu stores its markups as ordinary PDF annotations, so PyMuPDF can
read and write them. Review status is a hidden reply annotation (/IRT) whose
/State is one of the Review-model values.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pymupdf

STATUSES = ("Accepted", "Rejected", "Canceled", "Completed", "None")
RED = (1.0, 0.0, 0.0)


@dataclass
class Markup:
    page: int          # 0-based
    xref: int
    type: str
    author: str
    subject: str
    content: str
    rect: tuple[float, float, float, float]
    color: tuple[float, ...] | None
    status: str

    def as_dict(self) -> dict:
        return asdict(self)


def _irt_xref(doc: pymupdf.Document, xref: int) -> int | None:
    kind, value = doc.xref_get_key(xref, "IRT")
    if kind != "xref":
        return None
    m = re.match(r"(\d+) 0 R", value)
    return int(m.group(1)) if m else None


def _stamp_info(annot: pymupdf.Annot, author: str, subject: str, content: str) -> None:
    annot.set_info(title=author, subject=subject, content=content)


def add_cloud(page: pymupdf.Page, rect, text: str = "", author: str = "",
              color=RED) -> pymupdf.Annot:
    """Revision cloud around ``rect``. The cloud effect is set via /BE."""
    r = pymupdf.Rect(rect)
    pts = [r.tl, r.tr, r.br, r.bl]
    annot = page.add_polygon_annot(pts)
    annot.set_colors(stroke=color)
    annot.set_border(width=1.5)
    _stamp_info(annot, author, "Cloud", text)
    annot.update()
    page.parent.xref_set_key(annot.xref, "BE", "<</S/C/I 2>>")
    return annot


def add_text(page: pymupdf.Page, rect, text: str, author: str = "",
             color=RED, fontsize: float = 10) -> pymupdf.Annot:
    """Free-text callout."""
    annot = page.add_freetext_annot(pymupdf.Rect(rect), text, fontsize=fontsize,
                                    text_color=color)
    _stamp_info(annot, author, "Text Box", text)
    annot.update()
    return annot


def add_stamp(page: pymupdf.Page, rect, label: str, author: str = "",
              color=RED) -> pymupdf.Annot:
    """Text stamp such as 'REVISED' or 'NOT FOR CONSTRUCTION'."""
    r = pymupdf.Rect(rect)
    annot = page.add_freetext_annot(r, label.upper(), fontsize=max(8.0, r.height * 0.5),
                                    text_color=color,
                                    align=pymupdf.TEXT_ALIGN_CENTER)
    _stamp_info(annot, author, "Stamp", label)
    annot.update()
    return annot


def set_status(doc: pymupdf.Document, page_no: int, xref: int, status: str,
               author: str = "") -> int:
    """Set Bluebeam review status on a markup. Returns the reply's xref."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    page = doc[page_no]
    target = page.load_annot(xref)
    if target is None:
        raise KeyError(f"no annotation {xref} on page {page_no}")
    r = target.rect
    reply = page.add_text_annot(pymupdf.Rect(r.x0, r.y0, r.x0 + 1, r.y0 + 1), " ")
    reply.set_irt_xref(target.xref)
    reply.set_flags(30)  # hidden + print: no visible sticky note
    reply.set_info(title=author, creationDate=pymupdf.get_pdf_now(),
                   modDate=pymupdf.get_pdf_now())
    reply.update()
    doc.xref_set_key(reply.xref, "State", f"({status})")
    doc.xref_set_key(reply.xref, "StateModel", "(Review)")
    return reply.xref


def list_markups(doc: pymupdf.Document) -> list[Markup]:
    """All top-level markups, each with its latest review status."""
    out: list[Markup] = []
    statuses: dict[int, str] = {}
    for page in doc:
        for annot in page.annots() or []:
            parent = _irt_xref(doc, annot.xref)
            if parent is not None:
                kind, value = doc.xref_get_key(annot.xref, "State")
                if kind == "string":
                    statuses[parent] = value  # later replies win
                continue
            if annot.type[1] in ("Popup", "Link", "Widget"):
                continue
            info = annot.info
            out.append(Markup(
                page=page.number, xref=annot.xref, type=annot.type[1],
                author=info.get("title", ""), subject=info.get("subject", ""),
                content=info.get("content", ""), rect=tuple(annot.rect),
                color=annot.colors.get("stroke"), status="None"))
    for m in out:
        m.status = statuses.get(m.xref, "None")
    return out
