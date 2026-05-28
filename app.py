import streamlit as st
import sqlite3
import matplotlib.pyplot as plt
import os
import datetime
import random
from collections import Counter

# ---------------- CONFIG ----------------
st.set_page_config(page_title="AI Student System", layout="wide")

# ---------------- DB ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "study.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

# TABLES
c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS subjects (username TEXT, subject TEXT, PRIMARY KEY(username,subject))")
c.execute("CREATE TABLE IF NOT EXISTS marks (username TEXT, subject TEXT, mark INTEGER, date TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS notes (username TEXT, subject TEXT, content TEXT, PRIMARY KEY(username,subject))")
conn.commit()

# ---------------- UTIL ----------------
def clean(s): return s.strip().lower()

# ---------------- AI ----------------
def explain_notes(text):
    sentences = [s.strip() for s in text.split(".") if len(s) > 20]
    words = text.lower().split()
    freq = Counter(words)
    scored = [(sum(freq.get(w,0) for w in s.split()), s) for s in sentences]
    return ["👉 "+s for _,s in sorted(scored, reverse=True)[:5]]

def teacher_answer(q, text):
    sentences = text.split(".")
    scored = [(sum(word.lower() in s.lower() for word in q.split()), s) for s in sentences]
    return [s for _,s in sorted(scored, reverse=True)[:3]]

def generate_quiz(text):
    words = list(set([w for w in text.split() if len(w)>5]))
    quiz=[]
    for w in random.sample(words, min(5,len(words))):
        opts=random.sample(words, min(4,len(words)))
        if w not in opts:
            opts[0]=w
        random.shuffle(opts)
        quiz.append((w,opts))
    return quiz

def planner(subs, marks):
    plan=[]
    for s,m in sorted(zip(subs,marks), key=lambda x:x[1]):
        if m<50: plan.append(f"🔥 {s}: 2 hrs focus")
        elif m<75: plan.append(f"⚡ {s}: revise 1.5 hrs")
        else: plan.append(f"✅ {s}: light 1 hr")
    return plan

# ---------------- SESSION ----------------
if "user" not in st.session_state:
    st.session_state.user=None

# ---------------- LOGIN ----------------
if not st.session_state.user:
    st.title("🎓 AI Student System")
    u=st.text_input("Username")
    p=st.text_input("Password",type="password")

    if st.button("Login / Register"):
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p))
        if not c.fetchone():
            c.execute("INSERT INTO users VALUES (?,?)",(u,p))
            conn.commit()
        st.session_state.user=u
        st.rerun()
    st.stop()

user=st.session_state.user
today=str(datetime.date.today())

# ================= SUBJECT MANAGEMENT =================
st.sidebar.title(f"👤 {user}")
st.sidebar.markdown("### 📚 Manage Subjects")

c.execute("SELECT subject FROM subjects WHERE username=?", (user,))
saved_subjects=[s[0] for s in c.fetchall()]

if "subjects" not in st.session_state:
    st.session_state.subjects = saved_subjects if saved_subjects else ["math","science","english"]

new_subjects=[]
for i,sub in enumerate(st.session_state.subjects):
    col1,col2=st.sidebar.columns([4,1])
    with col1:
        new_subjects.append(st.text_input(f"Subject {i+1}", sub, key=f"s{i}"))
    with col2:
        if st.button("❌", key=f"d{i}"):
            st.session_state.subjects.pop(i)
            st.rerun()

st.session_state.subjects=new_subjects

if st.sidebar.button("➕ Add Subject"):
    st.session_state.subjects.append("new_subject")
    st.rerun()

if st.sidebar.button("💾 Save Subjects"):
    c.execute("DELETE FROM subjects WHERE username=?", (user,))
    for s in st.session_state.subjects:
        if s.strip():
            c.execute("INSERT INTO subjects VALUES (?,?)",(user,clean(s)))
    conn.commit()
    st.success("Saved ✅")
    st.rerun()

subjects=st.session_state.subjects

page=st.sidebar.radio("Navigate", ["Dashboard","AI Teacher","Quiz","Planner"]+subjects)

# ================= DASHBOARD =================
if page=="Dashboard":
    st.title("📊 Dashboard")

    marks=[]
    cols=st.columns(len(subjects))

    c.execute("SELECT subject,mark FROM marks WHERE username=? AND date=?", (user,today))
    today_data={s:m for s,m in c.fetchall()}

    for i,sub in enumerate(subjects):
        with cols[i]:
            val=today_data.get(clean(sub),50)
            marks.append(st.number_input(sub,0,100,val,key=sub))

    if st.button("💾 Save Marks"):
        for i,sub in enumerate(subjects):
            c.execute("INSERT INTO marks VALUES (?,?,?,?)",(user,clean(sub),marks[i],today))
        conn.commit()
        st.success("Saved")

    avg=sum(marks)/len(marks)
    c1,c2,c3=st.columns(3)
    c1.metric("Average", round(avg,1))
    c2.metric("Highest", max(marks))
    c3.metric("Lowest", min(marks))

    st.subheader("🥧 Performance")

    clean_data={clean(sub):marks[i] for i,sub in enumerate(subjects)}

    fig,ax=plt.subplots(figsize=(4,4))
    ax.pie(list(clean_data.values()),
           labels=[s.capitalize() for s in clean_data.keys()],
           autopct="%1.1f%%",
           startangle=90)
    ax.axis("equal")
    st.pyplot(fig)

    st.subheader("📉 Progress")
    c.execute("SELECT date, AVG(mark) FROM marks WHERE username=? GROUP BY date",(user,))
    data=c.fetchall()

    if data:
        d=[x[0] for x in data]
        m=[x[1] for x in data]
        fig,ax=plt.subplots()
        ax.plot(d,m,marker='o')
        ax.grid()
        st.pyplot(fig)

# ================= AI TEACHER =================
elif page=="AI Teacher":
    st.title("🧠 AI Teacher")

    subject=st.selectbox("Subject", subjects)
    q=st.text_area("Ask your doubt")

    if st.button("Answer"):
        c.execute("SELECT content FROM notes WHERE username=? AND subject=?",(user,clean(subject)))
        d=c.fetchone()
        if d:
            for ans in teacher_answer(q,d[0]):
                st.write("👉",ans)
        else:
            st.warning("Upload notes first")

# ================= QUIZ =================
elif page=="Quiz":
    st.title("🧪 Quiz")

    subject=st.selectbox("Subject", subjects)

    if st.button("Generate Quiz"):
        c.execute("SELECT content FROM notes WHERE username=? AND subject=?",(user,clean(subject)))
        d=c.fetchone()

        if d:
            st.session_state.quiz=generate_quiz(d[0])

    if "quiz" in st.session_state:
        score=0
        for i,(ans,opts) in enumerate(st.session_state.quiz):
            choice=st.radio(f"Q{i+1}: {ans}", opts, key=i)
            if choice==ans:
                score+=1

        if st.button("Submit"):
            st.success(f"Score: {score}/{len(st.session_state.quiz)}")

# ================= PLANNER =================
elif page=="Planner":
    st.title("📅 Study Planner")

    c.execute("SELECT subject,mark FROM marks WHERE username=? AND date=?", (user,today))
    data=c.fetchall()

    if data:
        subs=[d[0] for d in data]
        marks=[d[1] for d in data]

        for p in planner(subs,marks):
            st.write(p)
    else:
        st.warning("Enter marks first")

# ================= SUBJECT NOTES =================
else:
    st.title(f"📘 {page} Notes")

    c.execute("SELECT content FROM notes WHERE username=? AND subject=?", (user,clean(page)))
    d=c.fetchone()
    text=d[0] if d else ""

    content=st.text_area("Write Notes", value=text, height=200)

    if st.button("💾 Save Notes"):
        c.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?)",(user,clean(page),content))
        conn.commit()
        st.success("Saved")

    if text:
        if st.button("🧠 Explain Notes"):
            for line in explain_notes(text):
                st.write(line)