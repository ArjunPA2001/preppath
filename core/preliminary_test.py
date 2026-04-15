"""
Builds a deterministic preliminary test from the question bank.
No LLM involved — picks one is_preliminary=True question per concept.
"""
from sqlalchemy.orm import Session
import models


def build_preliminary_test(db: Session, section_ids: list[int] | None = None) -> list[dict]:
    """
    Return one preliminary question per concept for the given sections.

    Args:
        section_ids: restrict to these section IDs. If None, returns across all sections.
                     Callers should always pass section_ids scoped to the candidate's
                     learning path so candidates don't receive questions from other paths.
    """
    query = db.query(models.Question).filter(models.Question.is_preliminary == True)

    if section_ids is not None:
        query = query.filter(models.Question.section_id.in_(section_ids))

    questions = query.order_by(
        models.Question.section_id.asc(),
        models.Question.concept_tag.asc(),
    ).all()

    return [
        {
            "question_id": q.id,
            "concept_tag": q.concept_tag,
            "text": q.text,
            "section_id": q.section_id,
            "difficulty_band": q.difficulty_band,
        }
        for q in questions
    ]
