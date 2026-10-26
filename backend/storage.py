"""Encrypted file storage with a tamper-evident fingerprint.

Every upload is encrypted on disk (Fernet = AES-128 + HMAC). The key is generated on first
start and kept in instance/secret.key, so no extra secret is needed in .env (the course .env
may only contain PORTKEY_API_KEY / OPENAI_API_KEY).

Each stored file also gets a SHA-256 fingerprint of the exact bytes we keep, plus the upload
time. If a photo were swapped later, its fingerprint would no longer match the record.
"""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

import clock
import db
from config import FILES_DIR, KEY_PATH


def _fernet() -> Fernet:
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
    return Fernet(KEY_PATH.read_bytes())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(user_id: int, kind: str, name: str, mime: str, data: bytes, meta: dict | None = None,
         when: str | None = None) -> int:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    path = FILES_DIR / f"{secrets.token_hex(12)}.bin"
    path.write_bytes(_fernet().encrypt(data))
    return db.insert("files", user_id=user_id, kind=kind, name=name[:120], mime=mime, sha256=sha256(data),
                     size=len(data), path=path.name, meta=db.dumps(meta or {}), created_at=when or clock.stamp(user_id))


def load(file_id: int, user_id: int | None = None) -> tuple[dict, bytes]:
    row = db.one("SELECT * FROM files WHERE id = ?", (file_id,))
    if not row or (user_id is not None and row["user_id"] != user_id):
        raise FileNotFoundError(file_id)
    data = _fernet().decrypt((FILES_DIR / row["path"]).read_bytes())
    return row, data


def verify(file_id: int) -> bool:
    """True if the stored bytes still match the fingerprint recorded at upload."""
    row, data = load(file_id)
    return sha256(data) == row["sha256"]


def file_public(row: dict) -> dict:
    return {
        "id": row["id"], "kind": row["kind"], "name": row["name"], "mime": row["mime"],
        "sha256": row["sha256"], "size": row["size"], "uploaded_at": row["created_at"],
        "meta": db.loads(row.get("meta"), {}),
    }


def delete_user_files(user_id: int) -> None:
    for row in db.q("SELECT path FROM files WHERE user_id = ?", (user_id,)):
        p: Path = FILES_DIR / row["path"]
        if p.exists():
            p.unlink()
