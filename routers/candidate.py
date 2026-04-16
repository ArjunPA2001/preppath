"""
Candidate router.

Endpoints:
  POST  /candidates                      — create a new candidate (no path yet)
  GET   /candidates                      — list all candidates (executive / feeder view)
  GET   /candidates/{id}                 — get one candidate
  PUT   /candidates/{id}/pipeline        — assign a learning path
                                           → auto-creates a pending preliminary assessment
  GET   /candidates/{id}/progress        — channel, sections, covered concepts
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db
from core.preliminary_test import build_preliminary_test

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────────────

class CreateCandidateRequest(BaseModel):
    user_id: int


class AssignPipelineRequest(BaseModel):
    learning_path_id: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _candidate_dict(c: models.Candidate, user: models.User | None = None) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "name": user.name if user else "",
        "email": user.email if user else "",
        "learning_path_id": c.learning_path_id,
        "channel": c.channel,
        "level": c.level,
        "gaps": json.loads(c.gaps or "[]"),
        "strengths": json.loads(c.strengths or "[]"),
        "pre_improvement_channel": c.pre_improvement_channel,
        "interview_ready": c.interview_ready,
        "readiness_score": c.readiness_score,
        "plan_id": c.plan_id,
    }


def _user_for(db, candidate: models.Candidate) -> models.User | None:
    return db.query(models.User).filter_by(id=candidate.user_id).first() if candidate.user_id else None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("")
def create_candidate(body: CreateCandidateRequest, db: DBSession = Depends(get_db)):
    """
    Create a candidate profile for an existing user with role=candidate.
    Note: creating a user via POST /users with role=candidate does this automatically.
    Use this endpoint only when you need to manually create a candidate profile for an
    existing user (e.g. after changing their role to candidate via PUT /users/{id}).
    """
    user = db.query(models.User).filter_by(id=body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "candidate":
        raise HTTPException(
            status_code=400,
            detail=f"User '{user.email}' has role '{user.role}', not 'candidate'",
        )
    existing = db.query(models.Candidate).filter_by(user_id=body.user_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A candidate profile already exists for user {body.user_id}",
        )

    candidate = models.Candidate(
        user_id=body.user_id,
        channel="",
        level="",
        gaps=json.dumps([]),
        strengths=json.dumps([]),
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_dict(candidate, user)


@router.get("")
def list_candidates(db: DBSession = Depends(get_db)):
    """List all candidates with their current channel and readiness state."""
    candidates = db.query(models.Candidate).order_by(models.Candidate.id).all()

    # Build lookups
    path_ids = {c.learning_path_id for c in candidates if c.learning_path_id}
    paths = {}
    if path_ids:
        for lp in db.query(models.LearningPath).filter(models.LearningPath.id.in_(path_ids)).all():
            paths[lp.id] = lp.name

    user_ids = {c.user_id for c in candidates if c.user_id}
    users = {}
    if user_ids:
        for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all():
            users[u.id] = u

    return {
        "candidates": [
            {
                **_candidate_dict(c, users.get(c.user_id)),
                "learning_path_name": paths.get(c.learning_path_id, "") if c.learning_path_id else "",
            }
            for c in candidates
        ]
    }


@router.get("/{candidate_id}")
def get_candidate(candidate_id: int, db: DBSession = Depends(get_db)):
    candidate = db.query(models.Candidate).filter_by(id=candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _candidate_dict(candidate, _user_for(db, candidate))


@router.put("/{candidate_id}/pipeline")
def assign_pipeline(
    candidate_id: int,
    body: AssignPipelineRequest,
    db: DBSession = Depends(get_db),
):
    """
    Assign a (published) learning path to a candidate.

    On assignment:
      1. Sets candidate.learning_path_id
      2. Resets channel / level / gaps / strengths (fresh start on new path)
      3. Auto-creates a pending preliminary assessment so the candidate can
         immediately go to /test and take it — no separate create step needed.

    Architecture note (SDD §candidate router):
      PUT /candidates/{id}/pipeline → auto-build preliminary test → trigger Plan Gen
      Plan Gen runs AFTER the preliminary test is submitted (in assessment router).
    """
    candidate = db.query(models.Candidate).filter_by(id=candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    lp = db.query(models.LearningPath).filter_by(id=body.learning_path_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Learning path not found")
    if lp.status != "published":
        raise HTTPException(
            status_code=400,
            detail=f"Learning path '{lp.name}' is not published yet. Publish it first.",
        )

    # Assign path and reset candidate state for a fresh start
    candidate.learning_path_id = body.learning_path_id
    candidate.channel = ""
    candidate.level = ""
    candidate.gaps = json.dumps([])
    candidate.strengths = json.dumps([])
    candidate.pre_improvement_channel = None
    candidate.interview_ready = False
    candidate.plan_id = None
    db.commit()

    # Auto-build the preliminary test question list scoped to this path's sections
    path_section_ids = [
        s.id for s in db.query(models.Section).filter_by(learning_path_id=body.learning_path_id).all()
    ]
    questions = build_preliminary_test(db, section_ids=path_section_ids)

    user = _user_for(db, candidate)

    if not questions:
        # Path has no preliminary questions yet — still assign but warn
        return {
            "candidate": _candidate_dict(candidate, user),
            "preliminary_assessment_id": None,
            "warning": "No preliminary questions found for this path. Publish the path to generate questions.",
        }

    question_ids = [q["question_id"] for q in questions]

    # Cancel any existing pending preliminary assessment for this candidate
    existing = (
        db.query(models.Assessment)
        .filter_by(candidate_id=candidate_id, assessment_type="preliminary_test", status="pending")
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()

    # Create the new preliminary assessment
    assessment = models.Assessment(
        candidate_id=candidate_id,
        assessment_type="preliminary_test",
        session_id=None,
        status="pending",
        question_ids=json.dumps(question_ids),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return {
        "candidate": _candidate_dict(candidate, user),
        "preliminary_assessment_id": assessment.id,
        "preliminary_questions": questions,
        "message": f"Learning path '{lp.name}' assigned. Preliminary test is ready.",
    }


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

    # All sections for the candidate's learning path (in order)
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
        "candidate": _candidate_dict(candidate, _user_for(db, candidate)),
        "sections": sections,
        "completed_section_ids": list(completed_section_ids),
        "active_session": active_info,
    }
