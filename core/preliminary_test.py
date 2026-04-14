"""
Builds a deterministic preliminary test from the question bank.
No LLM involved — picks one is_preliminary=True question per concept.
"""
import json
from sqlalchemy.orm import Session
import models


def build_preliminary_test(db: Session, seniority: str = "mid") -> list[dict]:
    """
    Return one preliminary question per concept across ALL sections,
    ordered by section then concept for reproducibility.
    """
    questions = (
        db.query(models.Question)
        .filter(
            models.Question.is_preliminary == True,
            models.Question.seniority == seniority,
        )
        .order_by(models.Question.section_id.asc(), models.Question.concept_tag.asc())
        .all()
    )

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
