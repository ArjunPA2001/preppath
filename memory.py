"""
In-process session state.
Resets on server restart — acceptable for a hackathon.
"""
from collections import deque

MAX_HISTORY = 12  # 6 turns × 2 (user + assistant)

# session_id → deque of {"role": "user"|"assistant", "content": str}
_chat_histories: dict[int, deque] = {}

# session_id → set of question ids already shown in this session
_shown_questions: dict[int, set] = {}

# session_id → the question currently being discussed (persists until concept changes)
_current_question: dict[int, dict] = {}


def get_history(session_id: int) -> list[dict]:
    return list(_chat_histories.get(session_id, deque()))


def append_message(session_id: int, role: str, content: str) -> None:
    if session_id not in _chat_histories:
        _chat_histories[session_id] = deque(maxlen=MAX_HISTORY)
    _chat_histories[session_id].append({"role": role, "content": content})


def mark_shown(session_id: int, question_id: int) -> None:
    _shown_questions.setdefault(session_id, set()).add(question_id)


def get_shown(session_id: int) -> set:
    return _shown_questions.get(session_id, set())


def get_current_question(session_id: int) -> dict | None:
    return _current_question.get(session_id)


def set_current_question(session_id: int, question: dict) -> None:
    """Store the active question for a session. Call when concept changes."""
    _current_question[session_id] = question


def clear_session(session_id: int) -> None:
    _chat_histories.pop(session_id, None)
    _shown_questions.pop(session_id, None)
    _current_question.pop(session_id, None)
