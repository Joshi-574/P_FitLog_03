import pytest

from fitlog_coach import (
    is_fitlog_related_question,
    is_workout_report_question,
    require_fitlog_scope,
)


@pytest.mark.parametrize("question", [
    "How do I accept friend requests in FitCircle?",
    "Summarize my FitLog workout report.",
    "How many workouts did I record last week?",
    "Where is the Claude coach setting in the dashboard?",
    "What does this project's SQLite schema store?",
    "How do I use FitCircle?",
    "Tell me about FitLog.",
])
def test_fitlog_and_report_questions_are_in_scope(question):
    assert is_fitlog_related_question(question)
    require_fitlog_scope(question)


@pytest.mark.parametrize("question", [
    "Who won the football match?",
    "Give me a pasta recipe.",
    "What is the capital of France?",
    "How should I train for a marathon?",
    "Summarize my FitLog report and recommend a pasta recipe.",
    "",
    "x" * 2001,
])
def test_general_questions_are_blocked_locally(question):
    assert not is_fitlog_related_question(question)
    with pytest.raises(ValueError, match="only answers questions about the FitLog"):
        require_fitlog_scope(question)


def test_only_report_questions_include_personal_workout_context():
    assert is_workout_report_question("Summarize my FitLog workout report.")
    assert not is_workout_report_question("How do I accept friend requests in FitCircle?")
