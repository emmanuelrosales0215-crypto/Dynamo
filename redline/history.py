"""Per-user undo/redo as operations, not file snapshots.

Each user has their own undo and redo stacks per document, so undo reverses only
that person's own actions and leaves other people's edits alone. Operations
address markups by their stable id. If someone else has since deleted or
replaced the markup an operation needs, the undo is refused with a clear message
and the stale entry is dropped.
"""
from __future__ import annotations

import json

import pymupdf

from . import markups
from .db import connect

MAX_STEPS = 100


class Conflict(Exception):
    """The operation can't be applied because the markup changed underneath it."""


def _edit_fields(state: dict) -> dict:
    return {"rect": list(state["rect"]), "text": state["content"],
            "color": list(state["color"]) if state.get("color") else None}


def edit_op(before: dict, after: dict, fields: set[str]) -> dict:
    """Record only the fields the user asked to change (redrawing can nudge other fields)."""
    b, a = _edit_fields(before), _edit_fields(after)
    keys = [k for k in b if k in fields and b[k] != a[k]]
    return {"t": "edit", "id": after["id"],
            "before": {k: b[k] for k in keys}, "after": {k: a[k] for k in keys}}


def run(doc: pymupdf.Document, op: dict, undo: bool) -> None:
    """Apply an operation forwards (redo) or backwards (undo)."""
    t = op["t"]
    try:
        if t == "create":
            if undo:
                page, xref = markups.find(doc, op["snap"]["id"])
                markups.delete_markup(doc, page, xref)
            else:
                markups.restore(doc, op["snap"])
        elif t == "delete":
            if undo:
                markups.restore(doc, op["snap"])
            else:
                page, xref = markups.find(doc, op["snap"]["id"])
                markups.delete_markup(doc, page, xref)
        elif t == "edit":
            page, xref = markups.find(doc, op["id"])
            f = op["before" if undo else "after"]
            markups.update_markup(doc, page, xref, rect=f.get("rect"), text=f.get("text"),
                                  color=f.get("color"))
        elif t == "status":
            page, xref = markups.find(doc, op["id"])
            markups.set_status(doc, page, xref, op["before" if undo else "after"])
        else:
            raise ValueError(f"unknown operation {t}")
    except KeyError:
        raise Conflict("that markup was removed by someone else") from None
    except FileExistsError:
        raise Conflict("that markup already exists again") from None
    except ValueError as e:
        raise Conflict(str(e)) from None


def record(doc_id: str, user_id: int, op: dict) -> None:
    """Push a new operation on the user's undo stack and clear their redo stack."""
    with connect() as c:
        c.execute("DELETE FROM history WHERE doc_id=? AND user_id=? AND stack='redo'", (doc_id, user_id))
        c.execute("INSERT INTO history(doc_id,user_id,stack,op) VALUES(?,?,'undo',?)",
                  (doc_id, user_id, json.dumps(op)))
        c.execute("DELETE FROM history WHERE doc_id=? AND user_id=? AND stack='undo' AND id NOT IN ("
                  "SELECT id FROM history WHERE doc_id=? AND user_id=? AND stack='undo' "
                  "ORDER BY id DESC LIMIT ?)", (doc_id, user_id, doc_id, user_id, MAX_STEPS))


def peek(doc_id: str, user_id: int, stack: str) -> tuple[int, dict] | None:
    with connect() as c:
        row = c.execute("SELECT id, op FROM history WHERE doc_id=? AND user_id=? AND stack=? "
                        "ORDER BY id DESC LIMIT 1", (doc_id, user_id, stack)).fetchone()
    return (row["id"], json.loads(row["op"])) if row else None


def move(doc_id: str, user_id: int, entry_id: int, to_stack: str | None) -> None:
    """Move an entry to the other stack, or drop it (to_stack=None).

    Re-inserting gives it a fresh id so it is the newest entry on its new stack.
    """
    with connect() as c:
        row = c.execute("SELECT op FROM history WHERE id=?", (entry_id,)).fetchone()
        c.execute("DELETE FROM history WHERE id=?", (entry_id,))
        if row and to_stack:
            c.execute("INSERT INTO history(doc_id,user_id,stack,op) VALUES(?,?,?,?)",
                      (doc_id, user_id, to_stack, row["op"]))


def available(doc_id: str, user_id: int) -> dict:
    return {"can_undo": peek(doc_id, user_id, "undo") is not None,
            "can_redo": peek(doc_id, user_id, "redo") is not None}
