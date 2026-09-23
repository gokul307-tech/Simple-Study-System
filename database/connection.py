from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', email TEXT DEFAULT '', college TEXT DEFAULT '', course TEXT DEFAULT '', year TEXT DEFAULT '', semester TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, target_percentage REAL DEFAULT 75, color TEXT DEFAULT '#2563eb', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, name));
CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, name TEXT NOT NULL, difficulty TEXT DEFAULT 'Medium', priority TEXT DEFAULT 'Medium', completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(subject_id, name));
CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, filename TEXT NOT NULL, extracted_text TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS marks (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, exam_name TEXT NOT NULL, mark REAL NOT NULL, maximum REAL NOT NULL, date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS quizzes (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, difficulty TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS quiz_questions (id INTEGER PRIMARY KEY, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, question TEXT NOT NULL, options TEXT NOT NULL, correct_answer TEXT NOT NULL, explanation TEXT NOT NULL DEFAULT '', topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS quiz_attempts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE, score INTEGER NOT NULL, total INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quiz_answers (id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE, question_id INTEGER NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE, answer TEXT NOT NULL, correct INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS flashcards (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, front TEXT NOT NULL, back TEXT NOT NULL, difficulty TEXT DEFAULT 'Medium', due_date TEXT NOT NULL DEFAULT (date('now')), interval_days INTEGER NOT NULL DEFAULT 1, review_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS study_tasks (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, title TEXT NOT NULL, due_date TEXT, priority TEXT DEFAULT 'Medium', completed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS study_sessions (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL, topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL, duration_minutes INTEGER NOT NULL, confidence INTEGER, reflection TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS learning_progress (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE, mastery REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, topic_id));
CREATE TABLE IF NOT EXISTS achievements (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, title TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_achievements (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE, earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, achievement_id));
CREATE INDEX IF NOT EXISTS idx_subjects_user ON subjects(user_id); CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id); CREATE INDEX IF NOT EXISTS idx_marks_user ON marks(user_id); CREATE INDEX IF NOT EXISTS idx_sessions_user ON study_sessions(user_id); CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcards(user_id, due_date);
"""


def get_connection(path: Path | str = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(path: Path | str = DB_PATH) -> None:
    with get_connection(path) as connection:
        _prepare_legacy_tables(connection)
        connection.executescript(SCHEMA)
        _migrate_legacy(connection)
        connection.commit()


def _prepare_legacy_tables(connection: sqlite3.Connection) -> None:
    legacy_names = {"users": "legacy_users", "subjects": "legacy_subjects", "marks": "legacy_marks", "notes": "legacy_notes"}
    for table, legacy_table in legacy_names.items():
        row = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not row:
            continue
        columns = {item[1] for item in connection.execute(f"PRAGMA table_info({table})")}
        expected = {"users": "password_hash", "subjects": "user_id", "marks": "user_id", "notes": "user_id"}[table]
        if expected not in columns:
            connection.execute(f"ALTER TABLE {table} RENAME TO {legacy_table}")


def _migrate_legacy(connection: sqlite3.Connection) -> None:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "users" not in tables:
        return
    from auth.security import hash_password, looks_like_hash
    for row in connection.execute("SELECT username, password FROM legacy_users WHERE username IS NOT NULL") if "legacy_users" in tables else []:
        existing = connection.execute("SELECT id FROM users WHERE username=?", (row[0],)).fetchone()
        if existing:
            continue
        password = row[1] or "change-me"
        password_hash = password if looks_like_hash(password) else hash_password(password)
        connection.execute("INSERT INTO users(username,password_hash) VALUES (?,?)", (row[0], password_hash))
    legacy_subjects = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_subjects'").fetchone()
    if legacy_subjects:
        for row in connection.execute("SELECT username, subject FROM legacy_subjects"):
            user = connection.execute("SELECT id FROM users WHERE username=?", (row[0],)).fetchone()
            if not user or not row[1]: continue
            connection.execute("INSERT OR IGNORE INTO subjects(user_id,name) VALUES (?,?)", (user[0], row[1]))
    if "legacy_marks" in tables:
        for row in connection.execute("SELECT username, subject, mark, date FROM legacy_marks"):
            user = connection.execute("SELECT id FROM users WHERE username=?", (row[0],)).fetchone()
            subject = connection.execute("SELECT id FROM subjects WHERE user_id=? AND name=?", (user[0], row[1])).fetchone() if user else None
            if user and subject:
                exists = connection.execute("SELECT id FROM marks WHERE user_id=? AND subject_id=? AND date=? AND mark=?", (user[0], subject[0], row[3], row[2])).fetchone()
                if not exists: connection.execute("INSERT INTO marks(user_id,subject_id,exam_name,mark,maximum,date) VALUES (?,?,?,?,?,?)", (user[0], subject[0], "Legacy assessment", row[2], 100, row[3]))
    if "legacy_notes" in tables:
        for row in connection.execute("SELECT username, subject, content FROM legacy_notes"):
            user = connection.execute("SELECT id FROM users WHERE username=?", (row[0],)).fetchone()
            subject = connection.execute("SELECT id FROM subjects WHERE user_id=? AND name=?", (user[0], row[1])).fetchone() if user else None
            if user and subject and row[2]:
                connection.execute("INSERT INTO notes(user_id,subject_id,title,content) SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM notes WHERE user_id=? AND subject_id=?)", (user[0], subject[0], f"{row[1]} notes", row[2], user[0], subject[0]))
