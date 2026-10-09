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
| `ANTHROPIC_API_KEY` | unset | Turns on the AI review assistant (one shared server key) |
| `REDLINE_AI_DAILY_LIMIT` | 20 | AI reviews per user per day (UTC) |
| `REDLINE_AI_MODEL` | `claude-opus-5-5` | Claude model used for reviews |

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

## AI review assistant

Click **AI review** to have Claude look at the current sheet and its markups. It returns a short
summary and findings: unclear comments, unresolved items, possible conflicts, missing markups,
wording or unit problems. Each finding can point at a markup and propose better text.

- **Advice only.** Nothing changes until you click **Apply text** (which is an ordinary, undoable
  edit made as you) or **Show / Dismiss**. The review never edits the drawing.
- **Treats the sheet as data.** Markup text and sheet text go to the model as untrusted content; a
  markup that says "ignore your instructions" is reported as a finding, not followed.
- **Bounded cost.** One server key, so each user gets a daily limit. A failed review doesn't count
  against it. Reviews are recorded in the activity log.
- **What is sent:** a ~1600 px image of the sheet, the drawing's file name, and the id, author,
  text, status and position of each markup on that sheet. Don't enable it for drawings that
  can't leave your network.
- Uses the server-side refusal fallback (`fallbacks: "default"`), so a declined request is
  retried on a fallback model instead of failing.

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
| GET | `/ai/status` | `{enabled, limit, remaining}` for the signed-in user |
| POST | `/documents/{id}/review` | AI review of one sheet (`{page}`); 503 if no key, 429 at the daily limit |
| GET | `/documents/{id}/pages/{n}.png` | Render a page |
| GET | `/documents/{id}/file` | Download the marked-up PDF |

## Status and limits

- Tested on generated PDFs and in a headless browser with two signed-in users. Also run once
  against a real 13-sheet Civil 3D set marked up in Revu (162 markups, 156 with review status):
  every sheet opens, renders and keeps its appearance and annotation counts after saving, and
  editing text, setting status, undo and delete work on its callouts. Real files taught us that
  Civil 3D plots add hundreds of read-only "AutoCAD SHX Text" boxes (hidden here), that Revu stores a
  callout's cloud and arrow as grouped parts of the callout (shown as one markup), and that Revu keeps a
  rich-text copy of each note (kept in step on edit). **Still unverified in Revu itself**: that
  Revu opens the edited file and shows the edits and statuses as expected.
- Single server process only: edits are serialised with an in-process lock per drawing, and the
  login throttle is in memory. Running several workers would need file locks and a shared throttle.
- Serve over HTTPS and set `REDLINE_SECURE_COOKIES=1` before exposing it. There is no password
  reset, email, roles beyond owner/member, or admin screen yet.
- Markups made in Revu or other programs can have their text and review status changed, but not
  moved, resized or recoloured here (rebuilding them could lose properties). Only clouds, text boxes
  and stamps made in Redline can be moved or resized, and only those can be restored by undo after a
  delete. Deleting a Revu markup is permanent; the viewer says so.
- Revu auto-grows a note's box when text gets longer; Redline can't, so it warns when new text
  probably won't fit.
- Two people editing the same markup at once: last write wins.
- Revision clouds carry the cloud border-effect key (`/BE`), but the stored appearance is a plain
  polygon, so Revu may redraw the scallops on first edit.
- `studio.py` (Bluebeam Studio sessions) is an **unverified** skeleton and is not wired in. It needs
  Developer Portal access and a Bluebeam subscription; check every URL against Bluebeam's docs.
- **The AI review has not been run against the live Claude API** (no key was available while
  building it). Request building, response cleaning, limits, failure handling and the UI are tested
  with a fake client; the exact request shape (structured output + `fallbacks`) is written from
  the SDK docs. Run one real review and check the server log before relying on it.
- Viewer has no pan/fit-to-width.

## Provenance

All code here was written fresh for this repo. The open-source projects surveyed
(for example openrevu, AGPL-3.0) were used as design references only; no code was
copied, so no copyleft terms apply.
