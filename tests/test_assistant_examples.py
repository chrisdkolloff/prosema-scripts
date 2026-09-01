"""Placeholder example questions for the article assistant."""

from app.assistant.examples import EXAMPLE_QUESTIONS


def test_example_questions_are_unique_swiss_german():
    assert len(EXAMPLE_QUESTIONS) >= 8
    assert len(set(EXAMPLE_QUESTIONS)) == len(EXAMPLE_QUESTIONS)
    for question in EXAMPLE_QUESTIONS:
        assert question == question.strip()
        assert question
        assert "ß" not in question
        assert '"' not in question
