import pytest

from services.ai_service import MaterialChunk, ask_teacher, retrieve_chunks


MATERIALS = [
    MaterialChunk("Binary search repeatedly divides a sorted array into smaller halves.", "Algorithms", "Searching"),
    MaterialChunk("A stack follows last in first out ordering.", "Data Structures", "Stacks"),
]


def test_retrieval_returns_relevant_chunks_only():
    chunks = retrieve_chunks("What is binary search?", MATERIALS)
    assert chunks[0].topic == "Searching"
    assert len(chunks) <= 4


@pytest.mark.parametrize("mode, heading", [("Simple", "### Answer"), ("Detailed", "### Explanation"), ("Exam", "### Introduction")])
def test_offline_teacher_modes(mode, heading):
    answer, used_ai, count = ask_teacher("What is binary search?", "Algorithms", "Searching", MATERIALS, mode)
    assert not used_ai
    assert count == 1
    assert heading in answer
    assert "Binary search" in answer


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="Please enter a question"):
        ask_teacher("  ", "Algorithms", "", MATERIALS)


def test_no_relevant_notes_has_honest_fallback():
    answer, used_ai, _ = ask_teacher("What is thermodynamics?", "Algorithms", "", MATERIALS)
    assert not used_ai
    assert "couldn't find enough information" in answer.lower()
