"""Local scope checks for the FitLog Anthropic coach."""
import re


_APP_CONTEXT = (
    "fitlog", "fitcircle", "dashboard", "this app", "the app", "our app",
    "this project", "the project", "project code", "sqlite", "database",
    "api", "test suite", "tests",
)
_REPORT_CONTEXT = (
    "workout report", "workout history", "recorded workout", "recorded workouts",
    "logged workout", "logged workouts", "workout data", "my fitlog report",
    "my weekly workout report", "workouts this week", "workouts last week",
    "workouts this month", "workouts last month", "workouts recorded",
    "workouts did i record", "workouts have i recorded", "my workout minutes",
    "my workout count", "my workout duration", "my workout calories",
    "calories burned in my workouts", "my recorded calories", "my recorded steps",
    "my report", "exercise history",
)
_FITLOG_TOPICS = (
    "workout", "workouts", "exercise", "exercises", "fitness", "activity", "steps", "calories",
    "duration", "progress", "goal", "streak", "achievement", "challenge",
    "friend", "leaderboard", "privacy", "signup", "sign up", "login",
    "account", "report", "history", "backup", "restore", "database", "schema",
    "api", "test", "dashboard", "data", "coach", "claude", "bug", "error",
    "project", "feature", "features", "function", "functionality", "navigation", "setup",
    "friends", "challenges", "accounts",
    "how to use fitlog", "how do i use fitlog", "how to use fitcircle",
    "how do i use fitcircle", "what does fitlog", "what does fitcircle",
    "what is fitlog", "what is fitcircle",
    "tell me about fitlog", "tell me about fitcircle",
)
_OUT_OF_SCOPE_HINTS = (
    "recipe", "capital of", "president", "football", "movie", "song",
    "weather", "politics", "stock market", "cryptocurrency", "news",
    "celebrity", "restaurant", "tell me a joke", "homework", "translate",
    "travel itinerary", "meal plan", "diet plan", "workout plan",
    "training plan", "exercise routine", "how to cook", "recommend a workout",
)


def _has_any_phrase(text, phrases):
    return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases)


def is_fitlog_related_question(question):
    """Return true only when a question has FitLog context and a FitLog topic."""
    if not isinstance(question, str):
        return False
    text = re.sub(r"\s+", " ", question.casefold()).strip()
    if not text or len(text) > 2000:
        return False
    if _has_any_phrase(text, _OUT_OF_SCOPE_HINTS):
        return False
    has_app_context = _has_any_phrase(text, _APP_CONTEXT)
    has_report_context = _has_any_phrase(text, _REPORT_CONTEXT)
    has_topic = _has_any_phrase(text, _FITLOG_TOPICS)
    return has_topic and (has_app_context or has_report_context)


def is_workout_report_question(question):
    """Identify questions that need the signed-in user's report context."""
    if not isinstance(question, str):
        return False
    text = re.sub(r"\s+", " ", question.casefold()).strip()
    return _has_any_phrase(text, _REPORT_CONTEXT)


def require_fitlog_scope(question):
    """Raise before network access when a question is outside FitLog's scope."""
    if not is_fitlog_related_question(question):
        raise ValueError(
            "Claude Coach only answers questions about the FitLog/FitCircle app "
            "or your recorded workout report. Please ask a project-related question."
        )
