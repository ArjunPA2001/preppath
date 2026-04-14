import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db

router = APIRouter()


def _candidate_dict(c: models.Candidate) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "learning_path_id": c.learning_path_id,
        "channel": c.channel,
        "level": c.level,
        "gaps": json.loads(c.gaps or "[]"),
        "strengths": json.loads(c.strengths or "[]"),
        "pre_improvement_channel": c.pre_improvement_channel,
        "interview_ready": c.interview_ready,
        "plan_id": c.plan_id,
    }


@router.get("/{candidate_id}")
def get_candidate(candidate_id: int, db: DBSession = Depends(get_db)):
    candidate = db.query(models.Candidate).filter_by(id=candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _candidate_dict(candidate)


@router.get("/{candidate_id}/progress")
def get_progress(candidate_id: int, db: DBSession = Depends(get_db)):
    candidate = db.query(models.Candidate).filter_by(id=candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Most recent active session
    active_session = (
        db.query(models.Session)
        .filter_by(candidate_id=candidate_id, status="active")
        .order_by(models.Session.created_at.desc())
        .first()
    )

    # All sections for the candidate's learning path (in plan order if plan exists)
    sections_raw = (
        db.query(models.Section)
        .filter_by(learning_path_id=candidate.learning_path_id)
        .order_by(models.Section.order_index)
        .all()
    )

    sections = [
        {
            "id": s.id,
            "name": s.name,
            "concepts": json.loads(s.concepts or "[]"),
        }
        for s in sections_raw
    ]

    # Completed sessions per section (ended sessions where gate fired)
    completed_section_ids = set()
    ended_sessions = (
        db.query(models.Session)
        .filter_by(candidate_id=candidate_id, status="ended")
        .all()
    )
    for s in ended_sessions:
        covered = set(json.loads(s.covered_concepts or "[]"))
        required = set(json.loads(s.required_concepts or "[]"))
        if required and required.issubset(covered):
            completed_section_ids.add(s.section_id)

    active_info = None
    if active_session:
        active_info = {
            "id": active_session.id,
            "section_id": active_session.section_id,
            "channel": active_session.channel,
            "covered_concepts": json.loads(active_session.covered_concepts or "[]"),
            "required_concepts": json.loads(active_session.required_concepts or "[]"),
            "answer_count": active_session.answer_count,
            "current_concept_tag": active_session.current_concept_tag,
        }

    return {
        "candidate": _candidate_dict(candidate),
        "sections": sections,
        "completed_section_ids": list(completed_section_ids),
        "active_session": active_info,
    }
