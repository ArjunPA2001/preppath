"""
Selects the next question for a mentor session turn.

Band selection logic (from architecture diagram):
  - Foundation channel:   wrong/None → foundational,  partial → foundational,  correct → deepdive
  - Deepdive channel:     wrong/None → deepdive,       partial → deepdive,       correct → interview_ready
  - Simulation channel:   always → interview_ready
  - Improvement channel:  wrong/None → foundational,   partial → foundational,   correct → deepdive

Question fetch with two fallback layers:
  Layer 1: exclude questions already shown this session (in-memory set)
  Layer 2: exclude questions the candidate last answered correctly (mastered)
  Fallback A: drop Layer 2 (mastered exclusion) if pool is empty
  Fallback B: drop both filters — pick any matching concept+band
  Fallback C: trigger Question Gen Agent to refill the pool, then retry once
  Fallback D: return None → mentor responds freeform (generation also failed)
"""
import json  # used in Fallback D for concepts JSON parsing
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession
import models
import memory


BAND_MAP: dict[str, dict[str, str]] = {
    "foundation": {
        "wrong": "foundational",
        "partial": "foundational",
        "correct": "deepdive",
        None: "foundational",
    },
    "deepdive": {
        "wrong": "deepdive",
        "partial": "deepdive",
        "correct": "interview_ready",
        None: "deepdive",
    },
    "simulation": {
        "wrong": "interview_ready",
        "partial": "interview_ready",
        "correct": "interview_ready",
        None: "interview_ready",
    },
    "improvement": {
        "wrong": "foundational",
        "partial": "foundational",
        "correct": "deepdive",
        None: "foundational",
    },
}


def select_band(channel: str, last_quality: str | None) -> str:
    channel_map = BAND_MAP.get(channel, BAND_MAP["foundation"])
    return channel_map.get(last_quality, "foundational")


def _mastered_question_ids(db: DBSession, candidate_id: int) -> set[int]:
    """Question ids where the candidate last answered correctly (already mastered)."""
    rows = (
        db.query(models.CandidateQuestionHistory.question_id)
        .filter_by(candidate_id=candidate_id, last_quality="correct")
        .all()
    )
    return {r[0] for r in rows}


def fetch_question(
    db: DBSession,
    candidate_id: int,
    session_id: int,
    concept_tag: str,
    band: str,
    seniority: str = "mid",
) -> models.Question | None:
    """
    Return the best unseen question for this concept+band, or None if exhausted.
    """
    shown = memory.get_shown(session_id)
    mastered = _mastered_question_ids(db, candidate_id)

    base_query = (
        db.query(models.Question)
        .filter(
            models.Question.concept_tag == concept_tag,
            models.Question.difficulty_band == band,
            models.Question.seniority == seniority,
        )
        .order_by(func.random())
    )

    # Layer 1 + 2: exclude shown AND mastered
    q = _apply_exclusions(base_query, shown | mastered).first()
    if q:
        memory.mark_shown(session_id, q.id)
        return q

    # Fallback A: exclude only shown (allow mastered back in)
    q = _apply_exclusions(base_query, shown).first()
    if q:
        memory.mark_shown(session_id, q.id)
        return q

    # Fallback B: no exclusions at all
    q = base_query.first()
    if q:
        memory.mark_shown(session_id, q.id)
        return q

    # Fallback C: drop band filter too — just match concept
    q = (
        db.query(models.Question)
        .filter(
            models.Question.concept_tag == concept_tag,
            models.Question.seniority == seniority,
        )
        .order_by(func.random())
        .first()
    )
    if q:
        memory.mark_shown(session_id, q.id)
        return q

    # Fallback D: pool is completely empty for this concept — ask the agent to generate more
    print(f"[question_selector] Pool exhausted for {concept_tag}, triggering Question Gen Agent…")
    try:
        from agents import question_gen
        section = (
            db.query(models.Section)
            .join(models.Question, models.Section.id == models.Question.section_id, isouter=True)
            .filter(models.Question.concept_tag == concept_tag)
            .first()
        )
        if section is None:
            # No questions exist at all for this concept — find section by concept list
            all_sections = db.query(models.Section).all()
            for s in all_sections:
                if concept_tag in json.loads(s.concepts or "[]"):
                    section = s
                    break

        if section:
            added = question_gen.generate_for_concept(db, concept_tag, section, seniority)
            if added > 0:
                # Retry with the freshly generated questions
                q = (
                    db.query(models.Question)
                    .filter(
                        models.Question.concept_tag == concept_tag,
                        models.Question.difficulty_band == band,
                        models.Question.seniority == seniority,
                    )
                    .order_by(func.random())
                    .first()
                )
                if q:
                    memory.mark_shown(session_id, q.id)
                    return q
    except Exception as e:
        print(f"[question_selector] Question Gen fallback failed: {e}")

    return None  # Fallback D failed — mentor will handle freeform


def _apply_exclusions(query, exclude_ids: set[int]):
    if exclude_ids:
        query = query.filter(~models.Question.id.in_(exclude_ids))
    return query


def update_question_history(
    db: DBSession,
    candidate_id: int,
    question_id: int,
    quality: str,
) -> None:
    """Upsert the candidate's history for a given question."""
    row = (
        db.query(models.CandidateQuestionHistory)
        .filter_by(candidate_id=candidate_id, question_id=question_id)
        .first()
    )
    if row:
        row.last_quality = quality
        row.times_seen += 1
    else:
        db.add(
            models.CandidateQuestionHistory(
                candidate_id=candidate_id,
                question_id=question_id,
                last_quality=quality,
                times_seen=1,
            )
        )
    db.commit()
