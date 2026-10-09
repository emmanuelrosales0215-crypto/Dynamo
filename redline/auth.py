"""Username/password login with server-side sessions.

Passwords are hashed with scrypt. A session cookie carries a random token; only
its SHA-256 is stored, so a leaked database cannot be replayed as cookies.
CSRF: the cookie is SameSite=Lax and unsafe requests whose Origin differs from
the host are refused (see ``origin_guard`` in api.py).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel

from .db import connect

COOKIE = "redline_session"
SESSION_TTL = 14 * 86400
USERNAME = re.compile(r"[a-z0-9][a-z0-9_.-]{2,31}")
MIN_PASSWORD = 10
_N, _R, _P = 2**14, 8, 1
_DUMMY = None  # hash verified when the user does not exist, to even out timing


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                              n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc, bytes.fromhex(digest))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(username: str, password: str) -> int:
    username = username.strip().lower()
    if not USERNAME.fullmatch(username):
        raise ValueError("username must be 3-32 characters: letters, digits, . _ -")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    with connect() as c:
        try:
            return c.execute("INSERT INTO users(username, password_hash) VALUES(?,?)",
                             (username, hash_password(password))).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("that username is taken") from None


def user_count() -> int:
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def signup_open() -> bool:
    return user_count() == 0 or os.environ.get("REDLINE_ALLOW_SIGNUP", "") in ("1", "true")


def user_by_name(username: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT id, username FROM users WHERE username=?",
                        (username.strip().lower(),)).fetchone()
    return dict(row) if row else None


# ---- sessions

def start_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        c.execute("INSERT INTO sessions(token_hash, user_id, expires) VALUES(?,?,?)",
                  (_hash_token(token), user_id, time.time() + SESSION_TTL))
    return token


def end_session(token: str) -> None:
    with connect() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    with connect() as c:
        row = c.execute(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token_hash=? AND s.expires>?", (_hash_token(token), time.time())).fetchone()
    return dict(row) if row else None


def current_user(redline_session: str | None = Cookie(default=None)) -> dict:
    user = user_for_token(redline_session)
    if not user:
        raise HTTPException(401, "not signed in")
    return user


# ---- login throttle (in memory, per process)

_fails: dict[tuple[str, str], list[float]] = {}
MAX_FAILS, LOCK_SECONDS = 5, 60


def _throttled(key: tuple[str, str]) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < LOCK_SECONDS]
    _fails[key] = recent
    return len(recent) >= MAX_FAILS


# ---- routes

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax",
                        secure=os.environ.get("REDLINE_SECURE_COOKIES", "") in ("1", "true"))


@router.get("/status")
def status(redline_session: str | None = Cookie(default=None)) -> dict:
    user = user_for_token(redline_session)
    return {"user": user["username"] if user else None, "signup_open": signup_open()}


@router.post("/signup")
def signup(body: Credentials, response: Response) -> dict:
    if not signup_open():
        raise HTTPException(403, "sign-up is closed; ask an existing user or the administrator")
    try:
        uid = create_user(body.username, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _set_cookie(response, start_session(uid))
    return {"user": body.username.strip().lower()}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    key = (body.username.strip().lower(), request.client.host if request.client else "")
    if _throttled(key):
        raise HTTPException(429, "too many failed attempts; wait a minute and try again")
    with connect() as c:
        row = c.execute("SELECT id, password_hash FROM users WHERE username=?", (key[0],)).fetchone()
    global _DUMMY
    _DUMMY = _DUMMY or hash_password("not-a-real-password")
    ok = verify_password(body.password, row["password_hash"] if row else _DUMMY)
    if not (row and ok):
        _fails.setdefault(key, []).append(time.time())
        raise HTTPException(401, "wrong username or password")
    _fails.pop(key, None)
    _set_cookie(response, start_session(row["id"]))
    return {"user": key[0]}


@router.post("/logout")
def logout(response: Response, redline_session: str | None = Cookie(default=None)) -> dict:
    if redline_session:
        end_session(redline_session)
    response.delete_cookie(COOKIE)
    return {"user": None}
