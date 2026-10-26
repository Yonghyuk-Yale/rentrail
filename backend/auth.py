"""Accounts and sessions.

Passwords are never stored: we keep a salted PBKDF2-SHA256 hash (200,000 rounds). A login
creates a random session token kept in an HttpOnly cookie, so page scripts cannot read it.
Every query that touches user data filters by the logged-in user's id.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Request

import db

ROUNDS = 200_000
SESSION_DAYS = 7
COOKIE = "rentrail_session"
MODES = ("tenant", "sublessor", "subtenant")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ROUNDS).hex()
    return digest, salt


def create_user(email: str, name: str, password: str, lang: str = "en", is_demo: bool = False,
                mode: str = "tenant") -> int:
    email = email.strip().lower()
    if db.one("SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with this email already exists.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    digest, salt = hash_password(password)
    return db.insert("users", email=email, name=name.strip()[:60] or "Renter", pw_hash=digest, salt=salt,
                     lang=lang, is_demo=int(is_demo), mode=mode if mode in MODES else "tenant", created_at=db.now())


def verify(email: str, password: str) -> dict | None:
    user = db.one("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    if not user:
        hash_password(password)  # same work either way, so timing does not reveal which emails exist
        return None
    digest, _ = hash_password(password, user["salt"])
    return user if hmac.compare_digest(digest, user["pw_hash"]) else None


def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.insert("sessions", token=token, user_id=user_id, created_at=db.now(), expires_at=expires.isoformat())
    return token


def end_session(token: str | None) -> None:
    if token:
        db.ex("DELETE FROM sessions WHERE token = ?", (token,))


def current_user(request: Request, rentrail_session: str | None = Cookie(default=None)) -> dict:
    token = rentrail_session
    if not token:
        raise HTTPException(401, "Please log in.")
    row = db.one("SELECT * FROM sessions WHERE token = ?", (token,))
    if not row or row["expires_at"] < datetime.now(timezone.utc).isoformat():
        raise HTTPException(401, "Your session expired. Please log in again.")
    user = db.one("SELECT id, email, name, lang, demo_today, is_demo, mode FROM users WHERE id = ?", (row["user_id"],))
    if not user:
        raise HTTPException(401, "Please log in.")
    return user


def public_user(user: dict) -> dict:
    return {k: user[k] for k in ("id", "email", "name", "lang", "demo_today", "is_demo", "mode") if k in user}
