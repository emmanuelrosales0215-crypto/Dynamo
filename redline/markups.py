"""Read and write markups on drawing PDFs as standard PDF annotations.

Bluebeam Revu stores its markups as ordinary PDF annotations, so PyMuPDF can
read and write them. Review status is a hidden reply annotation (/IRT) whose
/State is one of the Review-model values.
"""
from __future__ import annotations

import html
import re
import uuid
from dataclasses import asdict, dataclass

import pymupdf

STATUSES = ("Accepted", "Rejected", "Canceled", "Completed", "None")
RED = (1.0, 0.0, 0.0)
# AutoCAD/Civil 3D PDF plots add one read-only box per text string for searching.
# They are not review markups, so they are kept out of lists and AI review.
SHX_AUTHOR = "AutoCAD SHX Text"


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
    native: bool = True     # made by this app (safe to rebuild); False for Revu/other programs
    grouped: bool = False   # has grouped parts (a callout's cloud and arrow)
    movable: bool = True    # geometry may be edited here: native and not grouped

    def as_dict(self) -> dict:
        return asdict(self)


def get_id(doc: pymupdf.Document, xref: int) -> str | None:
    kind, value = doc.xref_get_key(xref, "NM")
    return value if kind == "string" else None


def _set_id(doc: pymupdf.Document, xref: int, nm: str | None) -> None:
    """Name a markup we create and tag it as ours (private key, ignored by other programs)."""
    doc.xref_set_key(xref, "NM", f"({nm or uuid.uuid4().hex})")
    doc.xref_set_key(xref, "RedlineApp", "true")


def is_native(doc: pymupdf.Document, xref: int) -> bool:
    return doc.xref_get_key(xref, "RedlineApp")[1] == "true"


def _ensure_name(doc: pymupdf.Document, xref: int) -> None:
    if get_id(doc, xref) is None:
        doc.xref_set_key(xref, "NM", f"({uuid.uuid4().hex})")


def ensure_ids(doc: pymupdf.Document) -> bool:
    """Give every annotation a /NM name (Revu-made ones already have one)."""
    changed = False
    for page in doc:
        for annot in page.annots() or []:
            if get_id(doc, annot.xref) is None:
                _ensure_name(doc, annot.xref)
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


def _is_group_child(doc: pymupdf.Document, xref: int) -> bool:
    return doc.xref_get_key(xref, "RT")[1] == "/Group"


def _restore_rich_text(doc: pymupdf.Document, xref: int, rc: tuple[str, str], text: str | None) -> None:
    """Put back a FreeText's rich-text copy (/RC) that PyMuPDF drops when it redraws the box.

    Revu keeps its formatting there and re-reads it when you edit the note, so it must
    carry the current text. ``rc`` is the (type, value) pair read before the redraw.
    """
    kind, value = rc
    if kind != "string":
        return
    if text is not None:
        body = re.search(r"(<body\b[^>]*>)(.*)(</body>)", value, re.S)
        if not body:
            return
        first_p = re.search(r"<p\b[^>]*>", body.group(2))
        open_tag = first_p.group(0) if first_p else "<p>"
        paras = "".join(f"{open_tag}{html.escape(line, quote=False)}</p>"
                        for line in (text.split("\n") or [""]))
        value = value[:body.start(2)] + paras + value[body.end(2):]
    doc.xref_set_key(xref, "RC", pymupdf.get_pdf_str(value))


def text_overflows(doc: pymupdf.Document, xref: int, text: str) -> bool:
    """True if ``text`` probably won't fit the visible text area of a FreeText markup."""
    da = doc.xref_get_key(xref, "DA")[1]
    size = re.search(r"([\d.]+)\s+Tf", da)
    fs = float(size.group(1)) if size else 10.0
    kind, rd = doc.xref_get_key(xref, "RD")
    kind_r, rr = doc.xref_get_key(xref, "Rect")
    try:
        x0, y0, x1, y1 = [float(v) for v in rr.strip("[]").split()]
        l, t, r, b = ([float(v) for v in rd.strip("[]").split()] if kind == "array" else [0, 0, 0, 0])
    except ValueError:
        return False
    width = (x1 - x0) - l - r - 6
    height = (y1 - y0) - t - b - 6
    if width <= 0 or height <= 0:
        return False
    lines = 0
    for para in text.split("\n"):
        cur, n = "", 1
        for word in para.split():
            trial = (cur + " " + word).strip()
            if cur and pymupdf.get_text_length(trial, fontname="helv", fontsize=fs) > width:
                cur, n = word, n + 1
            else:
                cur = trial
        lines += n
    return lines * fs * 1.15 > height + 0.5


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
    reply.set_info(title=author, subject=f"Set to {status}",
                   creationDate=pymupdf.get_pdf_now(), modDate=pymupdf.get_pdf_now())
    reply.update()
    doc.xref_set_key(reply.xref, "Name", "/Note")
    doc.xref_set_key(reply.xref, "State", f"({status})")
    doc.xref_set_key(reply.xref, "StateModel", "(Review)")
    return reply.xref


def list_markups(doc: pymupdf.Document) -> list[Markup]:
    """Review markups with their latest status.

    Skipped: replies (they carry the review status), grouped parts (folded into their
    parent's rect), CAD text boxes, and popups/links/widgets.
    """
    out: list[Markup] = []
    statuses: dict[int, str] = {}
    parts: dict[int, list[pymupdf.Rect]] = {}
    for page in doc:
        for annot in page.annots() or []:
            parent = _irt_xref(doc, annot.xref)
            if parent is not None:
                kind, value = doc.xref_get_key(annot.xref, "State")
                if kind == "string":
                    statuses[parent] = value  # later replies win
                elif _is_group_child(doc, annot.xref):
                    parts.setdefault(parent, []).append(_rect(annot))
                continue
            if annot.type[1] in ("Popup", "Link", "Widget"):
                continue
            info = annot.info
            if info.get("title") == SHX_AUTHOR:
                continue
            out.append(Markup(
                id=get_id(doc, annot.xref) or "", page=page.number,
                xref=annot.xref, type=annot.type[1],
                author=info.get("title", ""), subject=info.get("subject", ""),
                content=info.get("content", ""), rect=tuple(_rect(annot)),
                color=annot.colors.get("stroke"), status="None",
                native=is_native(doc, annot.xref)))
    for m in out:
        m.status = statuses.get(m.xref, "None")
        if m.xref in parts:
            box = pymupdf.Rect(m.rect)
            for r in parts[m.xref]:
                box |= r
            m.rect, m.grouped = tuple(box), True
        m.movable = m.native and not m.grouped
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
    if rect is not None or color is not None:
        current = next(m for m in list_markups(doc) if m.xref == xref)
        if not current.movable:
            raise ValueError("This markup was made in another program or is grouped; "
                             "you can change its text and status here, but not move, resize or recolor it.")
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
        rc = doc.xref_get_key(xref, "RC")
        if rect is not None:
            annot.set_rect(pymupdf.Rect(rect))
        _set_info(doc, annot, info)
        annot.update(**({"text_color": tuple(color)} if color is not None else {}))
        _restore_rich_text(doc, xref, rc, text)
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
    snap["restorable"] = m.native and m.subject in RESTORABLE
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
