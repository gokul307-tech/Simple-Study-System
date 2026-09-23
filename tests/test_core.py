import sqlite3

import pytest

from auth.authentication import authenticate, register_user
from auth.security import hash_password, verify_password
from database.connection import get_connection, init_database
from database.repositories import Repository


@pytest.fixture
def connection(tmp_path):
    path = tmp_path / "test.db"
    init_database(path)
    with get_connection(path) as connection:
        yield connection


def test_password_hashing():
    encoded = hash_password("a secure password")
    assert encoded != "a secure password"
    assert verify_password("a secure password", encoded)
    assert not verify_password("wrong password", encoded)


def test_registration_login_and_duplicate(connection):
    ok, user_id = register_user(connection, "student", "a secure password", "Student")
    assert ok and int(user_id) > 0
    assert authenticate(connection, "student", "a secure password") == int(user_id)
    ok, message = register_user(connection, "student", "a secure password")
    assert not ok and "already" in message


def test_subject_notes_marks_and_isolation(connection):
    _, first = register_user(connection, "first", "a secure password")
    _, second = register_user(connection, "second", "a secure password")
    first_repo, second_repo = Repository(connection, int(first)), Repository(connection, int(second))
    first_repo.add_subject("Physics", 80)
    subject_id = first_repo.subjects()[0]["id"]
    first_repo.save_note(None, subject_id, None, "Motion", "Velocity is displacement over time.")
    first_repo.add_mark(subject_id, "CAT 1", 42, 50, "2026-09-23")
    assert len(first_repo.notes(subject_id)) == 1
    assert first_repo.marks(subject_id)[0]["percentage"] == 84.0
    assert second_repo.subjects() == []
    assert second_repo.notes() == []
