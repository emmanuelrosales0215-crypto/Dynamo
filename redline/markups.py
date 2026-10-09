"""Read and write markups on drawing PDFs as standard PDF annotations.

Bluebeam Revu stores its markups as ordinary PDF annotations, so PyMuPDF can
read and write them. Review status is a hidden reply annotation (/IRT) whose
/State is one of the Review-model values.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass

import pymupdf

STATUSES = ("Accepted", "Rejected", "Canceled", "Completed", "None")
RED = (1.0, 0.0, 0.0)


@dataclass
class Markup:
    id: str            # stable /NM name, survives edits and cloud rebuilds
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


def get_id(doc: pymupdf.Document, xref: int) -> str | None:
    kind, value = doc.xref_get_key(xref, "NM")
    return value if kind == "string" else None


def _set_id(doc: pymupdf.Document, xref: int, nm: str | None) -> None:
    doc.xref_set_key(xref, "NM", f"({nm or uuid.uuid4().hex})")


def ensure_ids(doc: pymupdf.Document) -> bool:
    """Give every annotation a /NM name (Revu-made ones already have one)."""
    changed = False
    for page in doc:
        for annot in page.annots() or []:
            if get_id(doc, annot.xref) is None:
                _set_id(doc, annot.xref, None)
                changed = True
    return changed


def find(doc: pymupdf.Document, markup_id: str) -> tuple[int, int]:
    """(page number, xref) of a top-level markup, or KeyError."""
    for page in doc:
        for annot in page.annots() or []:
            if get_id(doc, annot.xref) == markup_id and _irt_xref(doc, annot.xref) is None:
                return page.number, annot.xref
    raise KeyError(f"no markup {markup_id}")


def _irt_xref(doc: pymupdf.Document, xref: int) -> int | None:
    kind, value = doc.xref_get_key(xref, "IRT")
    if kind != "xref":
        return None
    m = re.match(r"(\d+) 0 R", value)
    return int(m.group(1)) if m else None


def _rect(annot: pymupdf.Annot) -> pymupdf.Rect:
    """Markup bounds; a polygon's vertices avoid the border padding in annot.rect."""
    pts = annot.vertices if annot.type[1] == "Polygon" else None
    if pts:
        return pymupdf.Rect(min(x for x, _ in pts), min(y for _, y in pts),
                            max(x for x, _ in pts), max(y for _, y in pts))
    return annot.rect


def _set_info(doc: pymupdf.Document, annot: pymupdf.Annot, info: dict) -> None:
    """set_info that can also clear the text (PyMuPDF skips an empty one)."""
    annot.set_info(info)
    if info.get("content", None) == "":
        doc.xref_set_key(annot.xref, "Contents", "()")


def _stamp_info(annot: pymupdf.Annot, author: str, subject: str, content: str) -> None:
    annot.set_info(title=author, subject=subject, content=content)


def add_cloud(page: pymupdf.Page, rect, text: str = "", author: str = "",
              color=RED, *, nm: str | None = None) -> pymupdf.Annot:
    """Revision cloud around ``rect``. The cloud effect is set via /BE."""
    r = pymupdf.Rect(rect)
    pts = [r.tl, r.tr, r.br, r.bl]
    annot = page.add_polygon_annot(pts)
    annot.set_colors(stroke=color)
    annot.set_border(width=1.5)
    _stamp_info(annot, author, "Cloud", text)
    annot.update()
    page.parent.xref_set_key(annot.xref, "BE", "<</S/C/I 2>>")
    _set_id(page.parent, annot.xref, nm)
    return annot


def add_text(page: pymupdf.Page, rect, text: str, author: str = "",
             color=RED, fontsize: float = 10, *, nm: str | None = None) -> pymupdf.Annot:
    """Free-text callout."""
    annot = page.add_freetext_annot(pymupdf.Rect(rect), text, fontsize=fontsize,
                                    text_color=color)
    _stamp_info(annot, author, "Text Box", text)
    annot.update()
    _set_id(page.parent, annot.xref, nm)
    return annot


def add_stamp(page: pymupdf.Page, rect, label: str, author: str = "",
              color=RED, *, nm: str | None = None) -> pymupdf.Annot:
    """Text stamp such as 'REVISED' or 'NOT FOR CONSTRUCTION'."""
    r = pymupdf.Rect(rect)
    annot = page.add_freetext_annot(r, label.upper(), fontsize=max(8.0, r.height * 0.5),
                                    text_color=color,
                                    align=pymupdf.TEXT_ALIGN_CENTER)
    _stamp_info(annot, author, "Stamp", label)
    annot.update()
    _set_id(page.parent, annot.xref, nm)
    return annot


def set_status(doc: pymupdf.Document, page_no: int, xref: int, status: str,
               author: str = "") -> int:
    """Set Bluebeam review status on a markup. Returns the reply's xref."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    page = doc[page_no]
    target = _find(page, xref)
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
                id=get_id(doc, annot.xref) or "", page=page.number, xref=annot.xref, type=annot.type[1],
                author=info.get("title", ""), subject=info.get("subject", ""),
                content=info.get("content", ""), rect=tuple(_rect(annot)),
                color=annot.colors.get("stroke"), status="None"))
    for m in out:
        m.status = statuses.get(m.xref, "None")
    return out


def _find(page: pymupdf.Page, xref: int) -> pymupdf.Annot:
    for annot in page.annots() or []:
        if annot.xref == xref:
            return annot
    raise KeyError(f"no annotation {xref} on page {page.number}")


def _load(doc: pymupdf.Document, page_no: int, xref: int) -> tuple[pymupdf.Page, pymupdf.Annot]:
    page = doc[page_no]
    annot = _find(page, xref)
    if _irt_xref(doc, xref) is not None:
        raise KeyError(f"no markup {xref} on page {page_no}")
    return page, annot


def update_markup(doc: pymupdf.Document, page_no: int, xref: int, *, rect=None,
                  text: str | None = None, color=None) -> int:
    """Change a markup's text, position/size or colour; omitted fields stay as they are.

    Returns the markup's xref. A cloud is rebuilt when its shape changes, because
    PyMuPDF cannot edit polygon vertices in place, so its xref changes and its
    review status is carried over to the new annotation.
    """
    page, annot = _load(doc, page_no, xref)
    kind = annot.type[1]
    info = annot.info
    if text is not None:
        info["content"] = text
    if kind == "Polygon" and (rect is not None or color is not None):
        current = next(m for m in list_markups(doc) if m.xref == xref)
        new_rect = rect if rect is not None else _rect(annot)
        new_color = tuple(color) if color is not None else (annot.colors.get("stroke") or RED)
        nm = get_id(doc, xref)
        delete_markup(doc, page_no, xref)
        new = add_cloud(page, new_rect, info["content"], info["title"], new_color, nm=nm)
        if current.status != "None":
            set_status(doc, page_no, new.xref, current.status)
        return new.xref
    if kind == "FreeText":
        if rect is not None:
            annot.set_rect(pymupdf.Rect(rect))
        _set_info(doc, annot, info)
        annot.update(**({"text_color": tuple(color)} if color is not None else {}))
        return xref
    _set_info(doc, annot, info)
    if color is not None:
        annot.set_colors(stroke=tuple(color))
    if rect is not None:
        annot.set_rect(pymupdf.Rect(rect))
    annot.update()
    return xref


def delete_markup(doc: pymupdf.Document, page_no: int, xref: int) -> None:
    """Delete a markup together with its review-status replies."""
    page, annot = _load(doc, page_no, xref)
    replies = [a for a in page.annots() if _irt_xref(doc, a.xref) == xref]
    for reply in replies:
        page.delete_annot(reply)
    page.delete_annot(_find(page, xref))


RESTORABLE = {"Cloud": add_cloud, "Text Box": add_text, "Stamp": add_stamp}


def snapshot(doc: pymupdf.Document, markup_id: str) -> dict:
    page_no, xref = find(doc, markup_id)
    m = next(m for m in list_markups(doc) if m.xref == xref)
    snap = m.as_dict()
    snap["restorable"] = m.subject in RESTORABLE
    return snap


def restore(doc: pymupdf.Document, snap: dict) -> None:
    """Recreate a deleted markup (same id, text, place and review status)."""
    try:
        find(doc, snap["id"])
    except KeyError:
        pass
    else:
        raise FileExistsError(f"markup {snap['id']} already exists")
    page = doc[snap["page"]]
    color = tuple(snap["color"]) if snap.get("color") else RED
    annot = RESTORABLE[snap["subject"]](page, snap["rect"], snap["content"],
                                        snap["author"], color, nm=snap["id"])
    if snap["status"] != "None":
        set_status(doc, page.number, annot.xref, snap["status"], snap["author"])
