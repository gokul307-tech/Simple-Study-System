from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import streamlit as st

from auth.authentication import authenticate, register_user
from config import DB_PATH
from database.connection import get_connection, init_database
from database.repositories import Repository
from services.ai_service import MaterialChunk, ask_teacher, make_quiz
from services.pdf_service import extract_pdf

st.set_page_config(page_title="Simple Study System", page_icon="📚", layout="wide")
init_database()


def db():
    return get_connection(DB_PATH)


def login():
    st.title("📚 Simple Study System")
    login_tab, register_tab = st.tabs(["Log in", "Create account"])
    with login_tab:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", type="primary"):
            with db() as connection:
                user_id = authenticate(connection, username, password)
            if user_id:
                st.session_state.user_id = user_id
                st.rerun()
            st.error("Invalid username or password.")
    with register_tab:
        username = st.text_input("Choose a username", key="new_username")
        name = st.text_input("Name (optional)")
        password = st.text_input("Create a password", type="password", key="new_password")
        confirm = st.text_input("Confirm password", type="password")
        if st.button("Create account", type="primary"):
            if password != confirm:
                st.error("Passwords do not match.")
            else:
                with db() as connection:
                    ok, message = register_user(connection, username, password, name)
                if ok:
                    st.success("Account created. You can now log in.")
                else:
                    st.error(message)


def subjects(repo):
    return {row["name"]: row["id"] for row in repo.subjects()}


def materials(connection, user_id, subject_id):
    rows = connection.execute("SELECT content FROM notes WHERE user_id=? AND subject_id=? UNION ALL SELECT extracted_text FROM documents WHERE user_id=? AND subject_id=?", (user_id, subject_id, user_id, subject_id)).fetchall()
    return [row[0] for row in rows if row[0]]


def teacher_materials(connection, user_id, subject_id, topic_id=None):
    query = "SELECT n.title, n.content, n.topic_id, t.name AS topic_name FROM notes n LEFT JOIN topics t ON t.id=n.topic_id WHERE n.user_id=? AND n.subject_id=?"
    params = [user_id, subject_id]
    if topic_id:
        query += " AND n.topic_id=?"
        params.append(topic_id)
    rows = connection.execute(query, params).fetchall()
    chunks = [MaterialChunk(row["content"], row["title"], row["topic_name"] or "") for row in rows if row["content"]]
    document_query = "SELECT d.filename, d.extracted_text, d.topic_id, t.name AS topic_name FROM documents d LEFT JOIN topics t ON t.id=d.topic_id WHERE d.user_id=? AND d.subject_id=?"
    document_params = [user_id, subject_id]
    if topic_id:
        document_query += " AND topic_id=?"
        document_params.append(topic_id)
    rows = connection.execute(document_query, document_params).fetchall()
    chunks.extend(MaterialChunk(row["extracted_text"], row["filename"], row["topic_name"] or "") for row in rows if row["extracted_text"])
    return chunks


def dashboard(repo, connection):
    st.title("Dashboard")
    user = connection.execute("SELECT * FROM users WHERE id=?", (repo.user_id,)).fetchone()
    st.subheader(f"Welcome{', ' + user['name'] if user['name'] else ''}")
    subject_rows, marks, sessions, tasks = repo.subjects(), repo.marks(), repo.sessions(), repo.tasks()
    if not subject_rows:
        st.info("You haven't added any subjects yet. Start in Subjects.")
        return
    percentages = [row["percentage"] for row in marks]
    cards = st.columns(4)
    cards[0].metric("Average mark", f"{sum(percentages) / len(percentages):.1f}%" if percentages else "No data")
    cards[1].metric("Study streak", f"{repo.streak()} day(s)")
    cards[2].metric("Study time", f"{sum(row['duration_minutes'] for row in sessions) // 60}h")
    cards[3].metric("Open tasks", sum(not row["completed"] for row in tasks))
    st.subheader("Subject performance")
    for subject in subject_rows:
        values = [row["percentage"] for row in marks if row["subject_id"] == subject["id"]]
        st.write(f"**{subject['name']}**: {sum(values) / len(values):.1f}%" if values else f"**{subject['name']}**: No marks yet")
        if values:
            st.progress(min(1.0, sum(values) / len(values) / 100))


def subjects_page(repo):
    st.title("Subjects and topics")
    with st.form("add_subject"):
        name = st.text_input("Subject name")
        target = st.number_input("Target percentage", 1.0, 100.0, 75.0)
        if st.form_submit_button("Add subject"):
            try:
                repo.add_subject(name, target)
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Enter a unique subject name.")
    for subject in repo.subjects():
        with st.expander(subject["name"]):
            rename = st.text_input("Rename", subject["name"], key=f"rename{subject['id']}")
            target = st.number_input("Target", 1.0, 100.0, float(subject["target_percentage"]), key=f"target{subject['id']}")
            left, right = st.columns(2)
            if left.button("Save subject", key=f"save{subject['id']}"):
                repo.update_subject(subject["id"], rename, target)
                st.rerun()
            if right.button("Delete subject", key=f"delete{subject['id']}"):
                repo.delete_subject(subject["id"])
                st.rerun()
            st.write("Topics")
            for topic in repo.topics(subject["id"]):
                st.write(f"{topic['name']} · {topic['difficulty']} · {topic['priority']}")
            with st.form(f"topic{subject['id']}"):
                topic = st.text_input("New topic")
                difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], key=f"difficulty{subject['id']}")
                priority = st.selectbox("Priority", ["Low", "Medium", "High"], key=f"priority{subject['id']}")
                if st.form_submit_button("Add topic") and topic.strip():
                    try:
                        repo.add_topic(subject["id"], topic, difficulty, priority)
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("That topic already exists.")


def notes_page(repo, connection):
    st.title("Notes and documents")
    available = subjects(repo)
    if not available:
        st.info("Add a subject before creating notes.")
        return
    selected = st.selectbox("Subject", list(available))
    subject_id = available[selected]
    topic_rows = {row["name"]: row["id"] for row in repo.topics(subject_id)}
    with st.form("note"):
        title = st.text_input("Title")
        topic = st.selectbox("Topic (optional)", ["None"] + list(topic_rows))
        content = st.text_area("Content", height=220)
        if st.form_submit_button("Save note"):
            if title.strip() and content.strip():
                repo.save_note(None, subject_id, topic_rows.get(topic), title, content)
                st.success("Note saved.")
            else:
                st.error("Title and content are required.")
    upload = st.file_uploader("Upload a text-based PDF", type=["pdf"])
    if upload and st.button("Extract and save PDF"):
        try:
            text = extract_pdf(upload)
            connection.execute("INSERT INTO documents(user_id,subject_id,filename,extracted_text) VALUES (?,?,?,?)", (repo.user_id, subject_id, upload.name, text))
            connection.commit()
            st.success("PDF text extracted and saved.")
        except ValueError as error:
            st.error(str(error))
    search = st.text_input("Search notes")
    for note in repo.notes(subject_id):
        if not search or search.lower() in (note["title"] + note["content"]).lower():
            with st.expander(note["title"]):
                st.write(note["content"])


def marks_page(repo):
    st.title("Marks")
    available = subjects(repo)
    if not available:
        st.info("Add a subject before recording marks.")
        return
    with st.form("mark"):
        subject = st.selectbox("Subject", list(available))
        exam = st.text_input("Assessment name", placeholder="CAT 1, Model, Assignment")
        mark = st.number_input("Mark", min_value=0.0, value=0.0)
        maximum = st.number_input("Maximum mark", min_value=0.1, value=100.0)
        when = st.date_input("Date", date.today())
        if st.form_submit_button("Save mark"):
            if not exam.strip() or mark > maximum:
                st.error("Enter an assessment name and a mark no greater than the maximum.")
            else:
                repo.add_mark(available[subject], exam, mark, maximum, when.isoformat())
                st.success(f"Saved: {mark:g}/{maximum:g} ({mark / maximum * 100:.1f}%).")
    rows = repo.marks()
    if rows:
        st.dataframe([dict(row) for row in rows], width="stretch")
    else:
        st.info("No marks available yet.")


def ai_page(repo, connection):
    st.title("AI Teacher")
    available = subjects(repo)
    if not available:
        st.info("Add notes and a subject first.")
        return
    selected = st.selectbox("Subject", list(available))
    subject_id = available[selected]
    topic_options = {"All topics": None}
    topic_options.update({row["name"]: row["id"] for row in repo.topics(subject_id)})
    topic = st.selectbox("Topic (optional)", list(topic_options))
    current_selection = (subject_id, topic_options[topic])
    if st.session_state.get("teacher_selection") not in (None, current_selection):
        st.session_state.pop("teacher_answer", None)
    mode = st.selectbox("Explanation mode", ["Simple", "Detailed", "Exam"])
    question = st.text_area("Your question", key="teacher_question")
    if st.button("Ask AI Teacher", type="primary"):
        try:
            answer, used_ai, chunk_count = ask_teacher(question, selected, topic if topic != "All topics" else "", teacher_materials(connection, repo.user_id, subject_id, topic_options[topic]), mode)
            st.session_state.teacher_answer = answer
            st.session_state.teacher_used_ai = used_ai
            st.session_state.teacher_chunk_count = chunk_count
            st.session_state.teacher_context = (question, selected, topic, subject_id, topic_options[topic])
            st.session_state.teacher_selection = current_selection
        except ValueError as error:
            st.error(str(error))
    if st.session_state.get("teacher_answer"):
        if st.session_state.get("teacher_used_ai"):
            st.caption(f"Based on {st.session_state.get('teacher_chunk_count', 0)} relevant study materials")
        else:
            st.caption("Offline Teacher · AI provider unavailable or not configured")
        st.markdown(st.session_state.teacher_answer)
        st.write("Quick actions")
        action_columns = st.columns(3)
        actions = [("Explain more simply", "Simple"), ("Give an example", "Detailed"), ("Give an exam answer", "Exam")]
        for column, (label, action_mode) in zip(action_columns, actions):
            if column.button(label):
                previous_question, previous_subject, previous_topic, previous_subject_id, previous_topic_id = st.session_state.teacher_context
                try:
                    answer, used_ai, chunk_count = ask_teacher(previous_question, previous_subject, previous_topic if previous_topic != "All topics" else "", teacher_materials(connection, repo.user_id, previous_subject_id, previous_topic_id), action_mode)
                    st.session_state.teacher_answer = answer
                    st.session_state.teacher_used_ai = used_ai
                    st.session_state.teacher_chunk_count = chunk_count
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))


def quiz_page(repo, connection):
    st.title("Quiz")
    available = subjects(repo)
    if not available:
        st.info("Add notes before generating a quiz.")
        return
    selected = st.selectbox("Subject", list(available))
    count = st.slider("Questions", 2, 10, 5)
    if st.button("Generate quiz"):
        questions = make_quiz(" ".join(materials(connection, repo.user_id, available[selected])), count)
        if questions:
            st.session_state.quiz, st.session_state.quiz_subject = questions, available[selected]
        else:
            st.warning("Add longer notes with explanatory sentences first.")
    questions = st.session_state.get("quiz", [])
    if questions:
        answers = [st.radio(f"{index + 1}. {question['question']}", question["options"], key=f"answer{index}") for index, question in enumerate(questions)]
        if st.button("Submit quiz"):
            score = sum(answer == question["answer"] for answer, question in zip(answers, questions))
            now = datetime.now().isoformat(timespec="minutes")
            cursor = connection.execute("INSERT INTO quizzes(user_id,subject_id,difficulty) VALUES (?,?,?)", (repo.user_id, st.session_state.quiz_subject, "Mixed"))
            quiz_id = cursor.lastrowid
            for question in questions:
                connection.execute("INSERT INTO quiz_questions(quiz_id,question,options,correct_answer,explanation) VALUES (?,?,?,?,?)", (quiz_id, question["question"], json.dumps(question["options"]), question["answer"], question["explanation"]))
            connection.execute("INSERT INTO quiz_attempts(user_id,quiz_id,score,total,started_at,ended_at) VALUES (?,?,?,?,?,?)", (repo.user_id, quiz_id, score, len(questions), now, now))
            connection.commit()
            st.success(f"Score: {score}/{len(questions)} ({score / len(questions) * 100:.0f}%)")


def planner_page(repo):
    st.title("Planner")
    available = subjects(repo)
    with st.form("task"):
        title = st.text_input("Task")
        subject = st.selectbox("Subject (optional)", ["None"] + list(available))
        due = st.date_input("Due date", date.today())
        priority = st.selectbox("Priority", ["Low", "Medium", "High"])
        if st.form_submit_button("Add task") and title.strip():
            repo.add_task(title, available.get(subject), due.isoformat(), priority)
            st.rerun()
    for task in repo.tasks():
        label = f"{task['title']} · {task['due_date'] or 'No date'} · {task['priority']}"
        if task["completed"]:
            st.write(f"~~{label}~~")
        elif st.button(f"Complete: {label}", key=f"complete{task['id']}"):
            repo.complete_task(task["id"])
            st.rerun()


def sessions_page(repo):
    st.title("Study sessions")
    available = subjects(repo)
    with st.form("session"):
        subject = st.selectbox("Subject", ["None"] + list(available))
        minutes = st.number_input("Duration (minutes)", 1, 720, 30)
        confidence = st.slider("Confidence", 1, 5, 3)
        reflection = st.text_area("What did you learn?")
        if st.form_submit_button("Save session"):
            repo.add_session(available.get(subject), None, minutes, confidence, reflection)
            st.success("Session recorded.")
    st.dataframe([dict(row) for row in repo.sessions()], width="stretch")


def analytics_page(repo):
    st.title("Analytics")
    marks, sessions, accuracy = repo.marks(), repo.sessions(), repo.quiz_accuracy()
    if not marks and not sessions and accuracy is None:
        st.info("Complete a quiz, mark, or study session to see analytics.")
        return
    cards = st.columns(3)
    cards[0].metric("Quiz accuracy", f"{accuracy:.1f}%" if accuracy is not None else "No data")
    cards[1].metric("Study hours", f"{sum(x['duration_minutes'] for x in sessions) / 60:.1f}")
    cards[2].metric("Current streak", f"{repo.streak()} day(s)")
    if marks:
        st.line_chart({"Percentage": [row["percentage"] for row in reversed(marks)]})


def profile_page(repo, connection):
    st.title("Profile")
    user = connection.execute("SELECT * FROM users WHERE id=?", (repo.user_id,)).fetchone()
    with st.form("profile"):
        name = st.text_input("Name", user["name"])
        email = st.text_input("Email", user["email"])
        course = st.text_input("Course", user["course"])
        year = st.text_input("Year", user["year"])
        semester = st.text_input("Semester", user["semester"])
        if st.form_submit_button("Save profile"):
            connection.execute("UPDATE users SET name=?,email=?,course=?,year=?,semester=? WHERE id=?", (name, email, course, year, semester, repo.user_id))
            connection.commit()
            st.success("Profile saved.")


if "user_id" not in st.session_state:
    st.session_state.user_id = None
if not st.session_state.user_id:
    login()
    st.stop()
connection = db()
repo = Repository(connection, st.session_state.user_id)
st.sidebar.title("Simple Study System")
page = st.sidebar.radio("Navigate", ["Dashboard", "Subjects", "Marks", "Notes", "AI Teacher", "Quiz", "Planner", "Study Sessions", "Analytics", "Profile"])
if st.sidebar.button("Log out"):
    st.session_state.clear()
    st.rerun()
if page == "Dashboard": dashboard(repo, connection)
elif page == "Subjects": subjects_page(repo)
elif page == "Marks": marks_page(repo)
elif page == "Notes": notes_page(repo, connection)
elif page == "AI Teacher": ai_page(repo, connection)
elif page == "Quiz": quiz_page(repo, connection)
elif page == "Planner": planner_page(repo)
elif page == "Study Sessions": sessions_page(repo)
elif page == "Analytics": analytics_page(repo)
else: profile_page(repo, connection)
