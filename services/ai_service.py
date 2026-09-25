from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import AI_MODEL, OPENROUTER_API_KEY, ai_enabled

LOGGER = logging.getLogger(__name__)
MAX_CHUNKS = 4
MAX_CHUNK_CHARS = 900
MAX_CONTEXT_CHARS = 3_200

SYSTEM_PROMPT = """You are the AI Teacher in a student learning application.
Teach clearly and accurately. Use the student's notes as the primary source when relevant.
Do not invent facts contradicted by the notes. If the notes are insufficient, say so and label general knowledge clearly.
Adapt to the requested mode. Prefer concise explanations, examples, important terms, steps, and exam-friendly structure.
Do not repeat the question or produce excessive length."""


@dataclass(frozen=True)
class MaterialChunk:
    text: str
    title: str = "Study material"
    topic: str = ""


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]


def split_chunks(text: str, title: str = "Study material", topic: str = "") -> list[MaterialChunk]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if len(part.strip()) >= 25]
    chunks: list[MaterialChunk] = []
    for index in range(0, len(sentences), 3):
        chunk = " ".join(sentences[index:index + 3]).strip()
        if chunk:
            chunks.append(MaterialChunk(chunk[:MAX_CHUNK_CHARS], title, topic))
    return chunks


def retrieve_chunks(question: str, materials: list[MaterialChunk | str], limit: int = MAX_CHUNKS) -> list[MaterialChunk]:
    query_terms = Counter(_tokens(question))
    candidates: list[MaterialChunk] = []
    for material in materials:
        candidates.extend(split_chunks(material) if isinstance(material, str) else [material])
    ranked: list[tuple[float, MaterialChunk]] = []
    for chunk in candidates:
        chunk_terms = Counter(_tokens(chunk.text))
        overlap = sum(min(query_terms[token], count) for token, count in chunk_terms.items() if token in query_terms)
        phrase_bonus = 1.5 if question.strip().lower() in chunk.text.lower() else 0
        ranked.append((overlap + phrase_bonus, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for score, chunk in ranked if score > 0][:limit]


def _offline_answer(question: str, chunks: list[MaterialChunk], mode: str) -> str:
    if not chunks:
        return "I couldn't find enough information about this in your current notes. Add a note or document for this subject and try again."
    evidence = " ".join(chunk.text for chunk in chunks)
    if mode == "Simple":
        return f"### Answer\nBased on your notes, {evidence}\n\n### Key Points\n- Review the highlighted note excerpts above.\n- Ask a more specific follow-up question for a narrower explanation."
    if mode == "Exam":
        return f"### Introduction\nThe available notes describe this topic as follows.\n\n### Explanation\n{evidence}\n\n### Conclusion\nUse the definition and main explanation from your notes, then add a relevant example in an exam answer."
    return f"### Answer\n{evidence}\n\n### Explanation\nThis answer is assembled from the most relevant excerpts in your notes.\n\n### Key Points\n- The excerpts are from your selected subject material.\n- The Offline Teacher does not add unsupported facts."


def _prompt(question: str, subject: str, topic: str, mode: str, chunks: list[MaterialChunk]) -> str:
    context = "\n\n".join(f"[{chunk.title}{' / ' + chunk.topic if chunk.topic else ''}]\n{chunk.text}" for chunk in chunks)
    context = context[:MAX_CONTEXT_CHARS]
    return f"Subject: {subject}\nTopic: {topic or 'Not selected'}\nMode: {mode}\nQuestion: {question}\n\nRelevant student notes:\n{context}"


def _llm_answer(question: str, subject: str, topic: str, mode: str, chunks: list[MaterialChunk]) -> str:
    if not ai_enabled():
        raise RuntimeError("AI provider is not configured")
    payload = json.dumps({"model": AI_MODEL, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": _prompt(question, subject, topic, mode, chunks)}], "temperature": 0.2, "max_tokens": 700}).encode()
    request = Request("https://openrouter.ai/api/v1/chat/completions", data=payload, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": "http://localhost"}, method="POST")
    with urlopen(request, timeout=25) as response:
        body = json.loads(response.read().decode("utf-8"))
    answer = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not answer:
        raise ValueError("The AI provider returned an empty answer.")
    return answer


def ask_teacher(question: str, subject: str, topic: str, materials: list[MaterialChunk | str], mode: str = "Simple") -> tuple[str, bool, int]:
    question = question.strip()
    if not question:
        raise ValueError("Please enter a question.")
    chunks = retrieve_chunks(question, materials)
    if not chunks:
        return _offline_answer(question, [], mode), False, 0
    try:
        return _llm_answer(question, subject, topic, mode, chunks), True, len(chunks)
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as error:
        LOGGER.warning("AI Teacher provider unavailable: %s", error)
        return _offline_answer(question, chunks, mode), False, len(chunks)


def explain(question: str, materials: list[str], mode: str = "College") -> str:
    answer, _, _ = ask_teacher(question, "", "", materials, mode)
    return answer


def make_quiz(material: str, count: int = 5) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", material) if len(s.strip().split()) >= 8]
    questions = []
    for sentence in sentences[:count * 2]:
        words = [w for w in re.findall(r"[A-Za-z]{5,}", sentence) if w.lower() not in {"which", "there", "their", "about", "these"}]
        if not words: continue
        answer = max(words, key=len)
        prompt = sentence.replace(answer, "_____,", 1).replace("_____,", "_____", 1)
        distractors = [w for other in sentences for w in re.findall(r"[A-Za-z]{5,}", other) if w.lower() != answer.lower()]
        options = list(dict.fromkeys([answer] + distractors))[:4]
        if len(options) < 2: continue
        questions.append({"question": prompt, "options": options, "answer": answer, "explanation": sentence})
        if len(questions) >= count: break
    return questions
