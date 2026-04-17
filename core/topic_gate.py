"""
Topic gate: tracks concept coverage within a session and fires when
all required concepts are covered with enough answers.

Rules (from architecture):
  - answer_count >= 3  AND  covered_concepts ⊇ required_concepts  → gate fires
  - quality="wrong" does NOT count toward coverage (must show partial/correct understanding)
  - For improvement channel sessions, required_concepts is set to the gap concepts only
    (handled at session creation time in the router — not here)

Concept weights (from the personalised plan):
  - weight 2.0 → concept needs 2 correct answers before it counts as covered
  - weight 1.0 → 1 correct answer (default)
  - weight 0.5 → 1 correct answer (minimum)
  Higher-weight concepts are the candidate's gaps — the mentor stays on them longer.
"""
import json
import math
from sqlalchemy.orm import Session as DBSession
import models


MIN_ANSWERS = 3  # minimum interactions before gate can fire


def record_answer_signal(
    db: DBSession,
    session_id: int,
    concept_tag: str,
    quality: str,
    concept_weights: dict[str, float] | None = None,
) -> None:
    """
    Called after every chat turn. Updates the session's covered concepts
    and answer count based on the signal the mentor agent emitted.

    concept_weights: from the candidate's personalised plan. A concept with
    weight 2.0 needs 2 correct answers before being marked covered.
    """
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        return

    session.answer_count += 1

    if quality == "correct":
        covered = set(json.loads(session.covered_concepts))
        if concept_tag not in covered:
            weight = (concept_weights or {}).get(concept_tag, 1.0)
            required_correct = max(1, math.ceil(weight))

            # Count how many correct answers already exist for this concept
            # (the current answer was committed before this function is called)
            correct_count = (
                db.query(models.SessionAnswer)
                .filter_by(session_id=session_id, concept_tag=concept_tag, quality="correct")
                .count()
            )

            if correct_count >= required_correct:
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
