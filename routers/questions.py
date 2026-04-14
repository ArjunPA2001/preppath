"""
Questions router.

POST /questions/generate          — generate questions for all concepts in a section
GET  /questions                   — fetch questions with optional filters
GET  /questions/status/{section_id} — how many questions exist per concept in a section
"""
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db
from agents import question_gen

router = APIRouter()


class GenerateRequest(BaseModel):
    section_id: int
    force: bool = False  # if True, generate even if questions already exist


@router.post("/generate")
def generate_questions(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
):
    """
    Trigger question generation for all concepts in a section.
    Runs synchronously and returns when done.
    Set force=True to add more questions even if the section already has some.
    """
    section = db.query(models.Section).filter_by(id=body.section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    concepts = json.loads(section.concepts or "[]")
    if not concepts:
        raise HTTPException(status_code=400, detail="Section has no concepts defined")

    if not body.force:
        # Check if all concepts already have all 9 combos
        all_full = True
        for concept in concepts:
            count = db.query(models.Question).filter_by(
                concept_tag=concept, section_id=section.id
            ).count()
            if count < 9:
                all_full = False
                break
        if all_full:
            return {
                "message": "All concepts already have full question sets. Use force=true to generate more.",
                "section_id": section.id,
                "concepts": concepts,
            }

    result = question_gen.generate_for_section(db, section)

    return {
        "message": f"Generation complete. Added {result['questions_added']} questions.",
        "section_id": section.id,
        "concepts": result["concepts"],
        "questions_added": result["questions_added"],
    }


@router.get("/status/{section_id}")
def section_question_status(section_id: int, db: DBSession = Depends(get_db)):
    """
    Returns how many questions exist per concept in a section,
    broken down by band and type. Useful for checking if generation is needed.
    """
    section = db.query(models.Section).filter_by(id=section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    concepts = json.loads(section.concepts or "[]")
    status = {}

    for concept in concepts:
        qs = db.query(models.Question).filter_by(
            concept_tag=concept, section_id=section_id
        ).all()

        breakdown = {}
        for q in qs:
            key = f"{q.difficulty_band}/{q.pattern_type}"
            breakdown[key] = breakdown.get(key, 0) + 1

        status[concept] = {
            "total": len(qs),
            "has_preliminary": any(q.is_preliminary for q in qs),
            "breakdown": breakdown,
            "missing": [
                f"{b}/{t}"
                for b in ["foundational", "deepdive", "interview_ready"]
                for t in ["conceptual", "scenario", "problem_solving"]
                if f"{b}/{t}" not in breakdown
            ],
        }

    return {"section_id": section_id, "section_name": section.name, "concepts": status}


@router.get("")
def list_questions(
    section_id: int | None = None,
    concept_tag: str | None = None,
    difficulty_band: str | None = None,
    pattern_type: str | None = None,
    db: DBSession = Depends(get_db),
):
    """Fetch questions with optional filters."""
    query = db.query(models.Question)

    if section_id is not None:
        query = query.filter_by(section_id=section_id)
    if concept_tag:
        query = query.filter_by(concept_tag=concept_tag)
    if difficulty_band:
        query = query.filter_by(difficulty_band=difficulty_band)
    if pattern_type:
        query = query.filter_by(pattern_type=pattern_type)

    questions = query.order_by(
        models.Question.concept_tag,
        models.Question.difficulty_band,
        models.Question.pattern_type,
    ).all()

    return {
        "total": len(questions),
        "questions": [
            {
                "id": q.id,
                "concept_tag": q.concept_tag,
                "text": q.text,
                "difficulty_band": q.difficulty_band,
                "pattern_type": q.pattern_type,
                "seniority": q.seniority,
                "is_preliminary": q.is_preliminary,
                "section_id": q.section_id,
            }
            for q in questions
        ],
    }
