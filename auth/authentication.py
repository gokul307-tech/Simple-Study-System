from __future__ import annotations

import re
import sqlite3

from .security import hash_password, verify_password

USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def validate_credentials(username: str, password: str) -> str | None:
    if not USERNAME.fullmatch(username.strip()): return "Username must be 3-32 letters, numbers, dots, dashes, or underscores."
    if len(password) < 8: return "Password must contain at least 8 characters."
    return None


def register_user(db: sqlite3.Connection, username: str, password: str, name: str = "") -> tuple[bool, str]:
    username = username.strip().lower(); error = validate_credentials(username, password)
    if error: return False, error
    try:
        cursor = db.execute("INSERT INTO users(username,password_hash,name) VALUES (?,?,?)", (username, hash_password(password), name.strip()))
        db.commit(); return True, str(cursor.lastrowid)
    except sqlite3.IntegrityError: return False, "That username is already registered."


def authenticate(db: sqlite3.Connection, username: str, password: str) -> int | None:
    row = db.execute("SELECT id,password_hash FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    return int(row[0]) if row and verify_password(password, row[1]) else None
