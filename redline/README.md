# Redline

Redline civil construction drawing PDFs and exchange markups with Bluebeam Revu.

Bluebeam stores markups as standard PDF annotations, so a redline made here opens
in Revu, and Revu markups can be listed and reviewed here. Review status uses the
hidden-reply (`/IRT`, `StateModel=Review`) convention Revu reads.

## Run

```
pip install -e .[dev]
uvicorn redline.api:app --reload
pytest
```

Open http://127.0.0.1:8000/ for the viewer. Set `REDLINE_DATA` to choose where uploaded PDFs are stored.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/documents` | Upload a PDF, returns `{id}` |
| GET | `/` | Browser viewer |
| GET | `/documents/{id}/info` | Page sizes in PDF points, plus `can_undo` / `can_redo` |
| POST | `/documents/{id}/undo`, `/redo` | Step back or forward through edits (409 if nothing to do) |
| GET | `/documents/{id}/markups` | List markups with review status |
| POST | `/documents/{id}/markups` | Add a `cloud`, `text` or `stamp` |
| PATCH | `/documents/{id}/markups/{page}/{xref}` | Change text, rect or colour (returns the xref, which changes for a resized cloud) |
| DELETE | `/documents/{id}/markups/{page}/{xref}` | Delete a markup and its review-status replies |
| POST | `/documents/{id}/markups/{page}/{xref}/status` | Set Accepted/Rejected/Canceled/Completed/None |
| GET | `/documents/{id}/pages/{n}.png` | Render a page |
| GET | `/documents/{id}/file` | Download the marked-up PDF |

## Status

- Markup read/write and review status: implemented and unit-tested on generated PDFs.
  Not yet tested against real Revu-authored files; do that first.
- Revision clouds carry the cloud border-effect key (`/BE`), but the stored appearance
  stream is a plain polygon, so Revu may redraw the scallops on first edit.
- `studio.py` (Bluebeam Studio sessions) is an **unverified** skeleton. It needs
  Developer Portal access and a Bluebeam subscription, and every URL must be checked
  against Bluebeam's docs. It is not wired into the API.
- No authentication or per-user access control on the API. Add before exposing it.
- Viewer (`static/index.html`, no build step): upload, page navigation, zoom, draw cloud/text/stamp
  by dragging, markup list per sheet, set review status. Verified in headless Chromium.
  Drag to move, drag the corner handle to resize, edit text, delete (button or Delete key).
  Undo/redo (buttons, Ctrl+Z, Ctrl+Shift+Z): each edit snapshots the PDF, last 50 kept,
  a new edit clears redo. History is per document and shared by everyone using it.
  No pan/fit-to-width or multi-user live updates yet.

## Provenance

All code here was written fresh for this repo. The open-source projects surveyed
(for example openrevu, AGPL-3.0) were used as design references only; no code was
copied, so no copyleft terms apply.
