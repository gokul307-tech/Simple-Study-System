from __future__ import annotations

import re
from collections import Counter


def retrieve_answer(question: str, materials: list[str], limit: int = 4) -> list[str]:
    sentences = [s.strip() for text in materials for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]
    terms = [word.lower() for word in re.findall(r"[A-Za-z]{3,}", question)]
    ranked = sorted(sentences, key=lambda sentence: sum(sentence.lower().count(term) for term in terms), reverse=True)
    return [sentence for sentence in ranked[:limit] if any(term in sentence.lower() for term in terms)] or ranked[:limit]


def explain(question: str, materials: list[str], mode: str = "College") -> str:
    answers = retrieve_answer(question, materials)
    if not answers: return "I could not find supporting material in your notes or documents. Add study material or ask a more specific question."
    prefix = "Offline Teacher: Based on your study material, "
    return prefix + " ".join(answers)


def make_quiz(material: str, count: int = 5) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", material) if len(s.strip().split()) >= 8]
    questions = []
    for sentence in sentences[:count * 2]:
        words = [w for w in re.findall(r"[A-Za-z]{5,}", sentence) if w.lower() not in {"which", "there", "their", "about", "these"}]
        if not words: continue
        answer = max(words, key=len)
        prompt = sentence.replace(answer, "_____", 1)
        distractors = [w for other in sentences for w in re.findall(r"[A-Za-z]{5,}", other) if w.lower() != answer.lower()]
        options = list(dict.fromkeys([answer] + distractors))[:4]
        if len(options) < 2: continue
        questions.append({"question": prompt, "options": options, "answer": answer, "explanation": sentence})
        if len(questions) >= count: break
    return questions


def summarize(material: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", material.strip())
    words = Counter(re.findall(r"[A-Za-z]{4,}", material.lower()))
    ranked = sorted(sentences, key=lambda s: sum(words[w.lower()] for w in re.findall(r"[A-Za-z]{4,}", s)), reverse=True)
    return " ".join(ranked[:5])
