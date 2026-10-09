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

Set `REDLINE_DATA` to choose where uploaded PDFs are stored.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/documents` | Upload a PDF, returns `{id}` |
| GET | `/documents/{id}/markups` | List markups with review status |
| POST | `/documents/{id}/markups` | Add a `cloud`, `text` or `stamp` |
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
- No viewer UI yet.

## Provenance

All code here was written fresh for this repo. The open-source projects surveyed
(for example openrevu, AGPL-3.0) were used as design references only; no code was
copied, so no copyleft terms apply.
