from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any


class Repository:
    def __init__(self, connection: sqlite3.Connection, user_id: int):
        self.db = connection
        self.user_id = user_id

    def subjects(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM subjects WHERE user_id=? ORDER BY name", (self.user_id,)).fetchall()

    def add_subject(self, name: str, target: float = 75) -> None:
        self.db.execute("INSERT INTO subjects(user_id,name,target_percentage) VALUES (?,?,?)", (self.user_id, name.strip(), target)); self.db.commit()

    def update_subject(self, subject_id: int, name: str, target: float) -> None:
        self.db.execute("UPDATE subjects SET name=?, target_percentage=? WHERE id=? AND user_id=?", (name.strip(), target, subject_id, self.user_id)); self.db.commit()

    def delete_subject(self, subject_id: int) -> None:
        self.db.execute("DELETE FROM subjects WHERE id=? AND user_id=?", (subject_id, self.user_id)); self.db.commit()

    def topics(self, subject_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM topics WHERE subject_id=? ORDER BY priority DESC,name", (subject_id,)).fetchall()

    def add_topic(self, subject_id: int, name: str, difficulty: str, priority: str) -> None:
        self.db.execute("INSERT INTO topics(subject_id,name,difficulty,priority) SELECT ?,?,?,? WHERE EXISTS (SELECT 1 FROM subjects WHERE id=? AND user_id=?)", (subject_id, name.strip(), difficulty, priority, subject_id, self.user_id)); self.db.commit()

    def notes(self, subject_id: int | None = None) -> list[sqlite3.Row]:
        query = "SELECT n.*,s.name subject_name,t.name topic_name FROM notes n JOIN subjects s ON s.id=n.subject_id LEFT JOIN topics t ON t.id=n.topic_id WHERE n.user_id=?"
        args: list[Any] = [self.user_id]
        if subject_id: query += " AND n.subject_id=?"; args.append(subject_id)
        return self.db.execute(query + " ORDER BY n.updated_at DESC", args).fetchall()

    def save_note(self, note_id: int | None, subject_id: int, topic_id: int | None, title: str, content: str) -> None:
        if note_id: self.db.execute("UPDATE notes SET subject_id=?,topic_id=?,title=?,content=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (subject_id, topic_id, title.strip(), content, note_id, self.user_id))
        else: self.db.execute("INSERT INTO notes(user_id,subject_id,topic_id,title,content) VALUES (?,?,?,?,?)", (self.user_id, subject_id, topic_id, title.strip(), content))
        self.db.commit()

    def marks(self, subject_id: int | None = None) -> list[sqlite3.Row]:
        q = "SELECT m.*,s.name subject_name, ROUND(100.0*m.mark/m.maximum,1) percentage FROM marks m JOIN subjects s ON s.id=m.subject_id WHERE m.user_id=?"; args: list[Any] = [self.user_id]
        if subject_id: q += " AND m.subject_id=?"; args.append(subject_id)
        return self.db.execute(q + " ORDER BY date DESC", args).fetchall()

    def add_mark(self, subject_id: int, exam: str, mark: float, maximum: float, when: str) -> None:
        self.db.execute("INSERT INTO marks(user_id,subject_id,exam_name,mark,maximum,date) VALUES (?,?,?,?,?,?)", (self.user_id, subject_id, exam.strip(), mark, maximum, when)); self.db.commit()

    def tasks(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT t.*,s.name subject_name FROM study_tasks t LEFT JOIN subjects s ON s.id=t.subject_id WHERE t.user_id=? ORDER BY t.completed,t.due_date", (self.user_id,)).fetchall()

    def add_task(self, title: str, subject_id: int | None, due_date: str, priority: str) -> None:
        self.db.execute("INSERT INTO study_tasks(user_id,title,subject_id,due_date,priority) VALUES (?,?,?,?,?)", (self.user_id, title.strip(), subject_id, due_date or None, priority)); self.db.commit()

    def complete_task(self, task_id: int) -> None:
        self.db.execute("UPDATE study_tasks SET completed=1 WHERE id=? AND user_id=?", (task_id, self.user_id)); self.db.commit()

    def sessions(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT ss.*,s.name subject_name,t.name topic_name FROM study_sessions ss LEFT JOIN subjects s ON s.id=ss.subject_id LEFT JOIN topics t ON t.id=ss.topic_id WHERE ss.user_id=? ORDER BY ended_at DESC", (self.user_id,)).fetchall()

    def add_session(self, subject_id: int | None, topic_id: int | None, minutes: int, confidence: int, reflection: str) -> None:
        end = datetime.now(); start = end - timedelta(minutes=minutes)
        self.db.execute("INSERT INTO study_sessions(user_id,subject_id,topic_id,started_at,ended_at,duration_minutes,confidence,reflection) VALUES (?,?,?,?,?,?,?,?)", (self.user_id, subject_id, topic_id, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), minutes, confidence, reflection)); self.db.commit()

    def quiz_accuracy(self) -> float | None:
        row = self.db.execute("SELECT 100.0*SUM(score)/NULLIF(SUM(total),0) FROM quiz_attempts WHERE user_id=?", (self.user_id,)).fetchone()
        return row[0] if row[0] is not None else None

    def streak(self) -> int:
        days = {row[0] for row in self.db.execute("SELECT DISTINCT date(ended_at) FROM study_sessions WHERE user_id=?", (self.user_id,))}
        current = date.today(); count = 0
        while current.isoformat() in days: count += 1; current -= timedelta(days=1)
        return count
