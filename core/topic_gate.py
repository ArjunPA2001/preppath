"""
Topic gate: tracks concept coverage within a session and fires when
all required concepts are covered with enough answers.

Rules (from architecture):
  - answer_count >= 3  AND  covered_concepts ⊇ required_concepts  → gate fires
  - quality="wrong" does NOT count toward coverage (must show partial/correct understanding)
  - For improvement channel sessions, required_concepts is set to the gap concepts only
    (handled at session creation time in the router — not here)
"""
import json
from sqlalchemy.orm import Session as DBSession
import models


MIN_ANSWERS = 3  # minimum interactions before gate can fire


def record_answer_signal(
    db: DBSession,
    session_id: int,
    concept_tag: str,
    quality: str,
) -> None:
    """
    Called after every chat turn. Updates the session's covered concepts
    and answer count based on the signal the mentor agent emitted.
    """
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        return

    session.answer_count += 1

    # Only mark a concept covered when the mentor explicitly signals full understanding.
    # "partial" means the candidate is on track but the mentor should keep working on it.
    # "wrong" means stay on the same concept entirely.
    if quality == "correct":
        covered = set(json.loads(session.covered_concepts))
        covered.add(concept_tag)
        session.covered_concepts = json.dumps(list(covered))

    session.current_concept_tag = concept_tag
    db.commit()


def check_topic_gate(db: DBSession, session_id: int) -> bool:
    """
    Returns True when the gate conditions are met:
      1. At least MIN_ANSWERS questions answered in this session
      2. All required concepts have been covered (partial or correct)
    """
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        return False

    if session.answer_count < MIN_ANSWERS:
        return False

    covered = set(json.loads(session.covered_concepts))
    required = set(json.loads(session.required_concepts))

    return required.issubset(covered)
