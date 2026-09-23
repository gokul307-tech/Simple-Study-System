# Simple Study System

Simple Study System is an offline-first Streamlit learning workspace. It combines authenticated student profiles, subjects and topics, notes and PDF extraction, quizzes, study tasks, sessions, analytics, and an Offline Teacher backed by the user's own material.

## Features

- Password-hashed registration and login with per-user data isolation.
- Subjects, target percentages, topics, difficulty, and priority.
- Multiple notes per subject, searchable notes, and text-based PDF extraction.
- Offline Teacher retrieval from saved notes and extracted documents.
- Meaningful local quizzes generated from explanatory note sentences, with stored attempts.
- Marks using any maximum score, tasks, study sessions, streaks, and analytics.
- SQLite foreign keys, indexes, transactions, and migration from the original `users`, `subjects`, `marks`, and `notes` tables.

## Setup on Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The existing `study.db` is migrated automatically on first start. Keep a backup before upgrading an important database.

## Configuration

Copy `.env.example` to `.env` if you need configuration values. Offline mode needs no API key. `STUDY_DB_PATH` can point to another SQLite file. The current AI implementation is intentionally offline-first; the service boundary in `services/ai_service.py` is the integration point for a future provider without changing page code.

## Tests

```powershell
python -m pytest -q
```

Tests use temporary databases and do not require API keys. PDF extraction requires `pypdf`; scanned PDFs without an embedded text layer are reported as non-extractable rather than silently accepted.

## Structure

- `app.py`: Streamlit navigation and page composition.
- `database/`: SQLite schema, migration, and user-scoped repository operations.
- `auth/`: validation, PBKDF2 password hashing, registration, and login.
- `services/`: offline retrieval/quiz logic and PDF extraction.
- `tests/`: authentication, persistence, calculations, and data-isolation checks.

## Troubleshooting

Delete only a disposable local database if it is corrupted; do not delete a production database to fix a migration issue. Check that the virtual environment is active and run `python -m py_compile app.py` for a quick syntax check. A PDF may be scanned or image-only; use OCR before uploading it.
