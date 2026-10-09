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

Open http://127.0.0.1:8000/. The first account created becomes the first user;
after that sign-up is closed unless you set `REDLINE_ALLOW_SIGNUP=1`.

| Setting | Default | Purpose |
|---|---|---|
| `REDLINE_DATA` | system temp dir `/redline` | Where PDFs and the SQLite database live. **Set this** for anything real. |
| `REDLINE_ALLOW_SIGNUP` | off | `1` lets anyone create an account |
| `REDLINE_SECURE_COOKIES` | off | `1` marks the session cookie Secure. Turn on behind HTTPS. |
| `REDLINE_MAX_UPLOAD_MB` | 100 | Largest PDF accepted |

## Accounts, sharing and history

- **Login:** username and password (scrypt-hashed, 10+ characters). Sessions are a random
  cookie (HttpOnly, SameSite=Lax); only its hash is stored. Five wrong passwords lock that
  username+address for a minute. Requests from another site's page are refused.
- **Private by default:** a drawing is visible only to its owner. The owner can share it with
  other users by username and revoke access. Others get a 404, not a 403, so ids don't leak.
  Only the owner can share or delete a drawing.
- **Authorship:** the author of every markup is the signed-in user, never taken from the request.
- **Per-user undo/redo:** each user has their own history per drawing (last 100 actions).
  Undo reverses only *your* actions and never touches other people's edits. If someone else
  has since deleted the markup your undo needs, you get a clear message and that step is dropped.
  Markups are tracked by a stable id (the PDF `/NM` name), which survives edits and resizing.
- **Activity log:** who did what on each drawing, visible to everyone with access.
- **Live-ish updates:** the viewer re-checks for other people's changes every few seconds.

## API

All routes except `/auth/*` and `/` need a signed-in session.

| Method | Path | Purpose |
|---|---|---|
| GET | `/auth/status` | `{user, signup_open}` |
| POST | `/auth/signup`, `/auth/login`, `/auth/logout` | Account and session |
| GET | `/documents` | Drawings you own or that were shared with you |
| POST | `/documents` | Upload a PDF, returns `{id, name}` |
| DELETE | `/documents/{id}` | Delete (owner only) |
| GET | `/documents/{id}/info` | Pages, role, owner, members, `can_undo`/`can_redo` |
| POST / DELETE | `/documents/{id}/share`, `/share/{username}` | Share or revoke (owner only) |
| GET | `/documents/{id}/activity` | Recent actions |
| GET | `/documents/{id}/markups` | List markups with id and review status |
| POST | `/documents/{id}/markups` | Add a `cloud`, `text` or `stamp` |
| PATCH | `/documents/{id}/markups/{markup_id}` | Change text, rect or colour |
| DELETE | `/documents/{id}/markups/{markup_id}` | Delete a markup and its review replies |
| POST | `/documents/{id}/markups/{markup_id}/status` | Accepted/Rejected/Canceled/Completed/None |
| POST | `/documents/{id}/undo`, `/redo` | Your own history (409 if nothing to do) |
| GET | `/documents/{id}/pages/{n}.png` | Render a page |
| GET | `/documents/{id}/file` | Download the marked-up PDF |

## Status and limits

- Tested on generated PDFs, in a headless browser with two signed-in users. **Not yet tested
  against real Revu-authored files**; do that first.
- Single server process only: edits are serialised with an in-process lock per drawing, and the
  login throttle is in memory. Running several workers would need file locks and a shared throttle.
- Serve over HTTPS and set `REDLINE_SECURE_COOKIES=1` before exposing it. There is no password
  reset, email, roles beyond owner/member, or admin screen yet.
- Undo can restore clouds, text boxes and stamps. Other markup types made in Revu (highlights,
  lines, ...) can be edited and undone, but deleting one is permanent; the viewer says so.
- Two people editing the same markup at once: last write wins.
- Revision clouds carry the cloud border-effect key (`/BE`), but the stored appearance is a plain
  polygon, so Revu may redraw the scallops on first edit.
- `studio.py` (Bluebeam Studio sessions) is an **unverified** skeleton and is not wired in. It needs
  Developer Portal access and a Bluebeam subscription; check every URL against Bluebeam's docs.
- Viewer has no pan/fit-to-width.

## Provenance

All code here was written fresh for this repo. The open-source projects surveyed
(for example openrevu, AGPL-3.0) were used as design references only; no code was
copied, so no copyleft terms apply.
