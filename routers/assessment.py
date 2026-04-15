"""
Assessment router.

Handles:
  POST /assessments                 — create a new assessment (preliminary, mock, or topic_gate)
  GET  /assessments/{id}            — fetch a pending assessment's questions
  POST /assessments/{id}/submit     — submit answers and trigger evaluation
  GET  /assessments/{id}/result     — fetch the stored result
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db
from core.preliminary_test import build_preliminary_test
from agents import evaluator, plan_gen

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────────────

class CreateAssessmentRequest(BaseModel):
    candidate_id: int
    assessment_type: str        # "preliminary_test" | "mock_interview"
    session_id: int | None = None


class AnswerItem(BaseModel):
    question_id: int
    answer: str


class SubmitAssessmentRequest(BaseModel):
    answers: list[AnswerItem]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _apply_eval_result(candidate: models.Candidate, result: dict, db: DBSession) -> None:
    """Write evaluator result back to the candidate row."""
    new_channel = result.get("channel", "foundation")

    # Improvement channel logic: save return channel before entering
    if new_channel == "improvement" and candidate.channel != "improvement":
        candidate.pre_improvement_channel = candidate.channel
    elif candidate.channel == "improvement" and new_channel != "improvement":
        candidate.pre_improvement_channel = None

    candidate.channel = new_channel
    candidate.level = result.get("level", "mid")
    candidate.gaps = json.dumps(result.get("gaps", []))
    candidate.strengths = json.dumps(result.get("strengths", []))

    # Interview-ready flag when candidate reaches simulation channel
    if new_channel == "simulation":
        candidate.interview_ready = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("")
def create_assessment(body: CreateAssessmentRequest, db: DBSession = Depends(get_db)):
    candidate = db.query(models.Candidate).filter_by(id=body.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if body.assessment_type == "preliminary_test":
        # If PUT /pipeline already pre-created a pending preliminary assessment, reuse it
        existing = (
            db.query(models.Assessment)
            .filter_by(candidate_id=body.candidate_id, assessment_type="preliminary_test", status="pending")
            .first()
        )
        if existing:
            question_ids = json.loads(existing.question_ids or "[]")
            qs = db.query(models.Question).filter(models.Question.id.in_(question_ids)).all()
            q_map = {q.id: q for q in qs}
            questions = [
                {"question_id": qid, "text": q_map[qid].text, "concept_tag": q_map[qid].concept_tag}
                for qid in question_ids if qid in q_map
            ]
            return {
                "assessment_id": existing.id,
                "assessment_type": "preliminary_test",
                "questions": questions,
            }

        # No pre-created assessment — build one fresh scoped to this candidate's path
        path_section_ids = None
        if candidate.learning_path_id:
            path_section_ids = [
                s.id for s in db.query(models.Section).filter_by(learning_path_id=candidate.learning_path_id).all()
            ]
        questions = build_preliminary_test(db, section_ids=path_section_ids)
        if not questions:
            raise HTTPException(status_code=500, detail="No preliminary questions found in database")
        question_ids = [q["question_id"] for q in questions]
    elif body.assessment_type == "mock_interview":
        # For mock interview: pull all interview_ready questions from the current session's section
        if not body.session_id:
            raise HTTPException(status_code=400, detail="session_id required for mock_interview")
        session = db.query(models.Session).filter_by(id=body.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        qs = (
            db.query(models.Question)
            .filter_by(section_id=session.section_id, difficulty_band="interview_ready")
            .all()
        )
        questions = [{"question_id": q.id, "text": q.text, "concept_tag": q.concept_tag} for q in qs]
        question_ids = [q.id for q in qs]
    elif body.assessment_type == "topic_gate":
        # Advancement test: one question per concept at the next-level band
        if not body.session_id:
            raise HTTPException(status_code=400, detail="session_id required for topic_gate")
        session = db.query(models.Session).filter_by(id=body.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Determine the target band based on current channel
        channel = candidate.channel or "foundation"
        CHANNEL_NEXT_BAND = {
            "foundation": "deepdive",
            "deepdive": "interview_ready",
            "simulation": "interview_ready",
            "improvement": "deepdive",
        }
        target_band = CHANNEL_NEXT_BAND.get(channel, "deepdive")

        # One question per concept (prefer target band, fall back to any band)
        sec = db.query(models.Section).filter_by(id=session.section_id).first()
        concepts = json.loads(sec.concepts or "[]") if sec else []
        questions = []
        question_ids = []
        for concept in concepts:
            q = (
                db.query(models.Question)
                .filter_by(
                    section_id=session.section_id,
                    concept_tag=concept,
                    difficulty_band=target_band,
                )
                .first()
            )
            if not q:
                # Fallback: any band for this concept
                q = (
                    db.query(models.Question)
                    .filter_by(section_id=session.section_id, concept_tag=concept)
                    .first()
                )
            if q:
                questions.append({"question_id": q.id, "text": q.text, "concept_tag": q.concept_tag})
                question_ids.append(q.id)

        if not questions:
            raise HTTPException(status_code=500, detail="No questions available for advancement test")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown assessment_type: {body.assessment_type}")

    assessment = models.Assessment(
        candidate_id=body.candidate_id,
        assessment_type=body.assessment_type,
        session_id=body.session_id,
        status="pending",
        question_ids=json.dumps(question_ids),
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return {
        "assessment_id": assessment.id,
        "assessment_type": body.assessment_type,
        "questions": questions,
    }


@router.get("/{assessment_id}")
def get_assessment(assessment_id: int, db: DBSession = Depends(get_db)):
    """Fetch an existing assessment's questions (for loading an advancement test from a link)."""
    assessment = db.query(models.Assessment).filter_by(id=assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    question_ids = json.loads(assessment.question_ids or "[]")
    qs = db.query(models.Question).filter(models.Question.id.in_(question_ids)).all()
    q_map = {q.id: q for q in qs}

    questions = [
        {
            "question_id": qid,
            "text": q_map[qid].text if qid in q_map else "",
            "concept_tag": q_map[qid].concept_tag if qid in q_map else "",
        }
        for qid in question_ids
        if qid in q_map
    ]

    return {
        "assessment_id": assessment.id,
        "assessment_type": assessment.assessment_type,
        "status": assessment.status,
        "candidate_id": assessment.candidate_id,
        "questions": questions,
    }


@router.post("/{assessment_id}/submit")
def submit_assessment(
    assessment_id: int,
    body: SubmitAssessmentRequest,
    db: DBSession = Depends(get_db),
):
    assessment = db.query(models.Assessment).filter_by(id=assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if assessment.status != "pending":
        raise HTTPException(status_code=400, detail="Assessment already submitted")

    # Save answers
    for item in body.answers:
        db.add(
            models.AssessmentAnswer(
                assessment_id=assessment_id,
                question_id=item.question_id,
                candidate_answer=item.answer,
            )
        )
    assessment.status = "submitted"
    db.commit()

    # Build Q&A pairs for the evaluator
    answer_map = {item.question_id: item.answer for item in body.answers}
    question_ids = json.loads(assessment.question_ids)
    questions = db.query(models.Question).filter(models.Question.id.in_(question_ids)).all()

    qa_pairs = [
        {
            "question": q.text,
            "answer": answer_map.get(q.id, ""),
            "concept_tag": q.concept_tag,
        }
        for q in questions
    ]

    # Get rubric for the relevant section(s)
    section_ids = list({q.section_id for q in questions})
    rubric_parts = []
    for sid in section_ids:
        sec = db.query(models.Section).filter_by(id=sid).first()
        if sec and sec.rubric:
            rubric_parts.append(sec.rubric)
    rubric_text = "\n\n".join(rubric_parts) or "Evaluate for technical accuracy, depth, and clarity."

    # Build candidate context
    candidate = db.query(models.Candidate).filter_by(id=assessment.candidate_id).first()
    candidate_context = {
        "level": candidate.level or "mid",
        "channel": candidate.channel or "foundation",
        "gaps": json.loads(candidate.gaps or "[]"),
        "strengths": json.loads(candidate.strengths or "[]"),
    }

    # Call evaluator
    result = evaluator.evaluate(
        assessment_type=assessment.assessment_type,
        qa_pairs=qa_pairs,
        candidate_context=candidate_context,
        rubric=rubric_text,
    )

    # Persist result
    assessment.result = json.dumps(result)
    assessment.status = "evaluated"

    # Apply result to candidate
    _apply_eval_result(candidate, result, db)

    # If this is a preliminary test, generate the learning plan
    if assessment.assessment_type == "preliminary_test":
        sections_raw = (
            db.query(models.Section)
            .filter_by(learning_path_id=candidate.learning_path_id)
            .order_by(models.Section.order_index)
            .all()
        )
        sections_for_plan = [
            {
                "id": s.id,
                "name": s.name,
                "concepts": json.loads(s.concepts or "[]"),
            }
            for s in sections_raw
        ]

        plan_data = plan_gen.generate_plan(
            candidate_level=result.get("level", "mid"),
            candidate_channel=result.get("channel", "foundation"),
            gaps=result.get("gaps", []),
            strengths=result.get("strengths", []),
            sections=sections_for_plan,
        )

        plan = models.CandidatePlan(
            candidate_id=candidate.id,
            section_order=json.dumps(plan_data.get("section_order", [])),
            concept_weights=json.dumps(plan_data.get("concept_weights", {})),
            pattern_weights=json.dumps(plan_data.get("pattern_weights", {})),
            difficulty_start=json.dumps(plan_data.get("difficulty_start", {})),
        )
        db.add(plan)
        db.flush()
        candidate.plan_id = plan.id

    db.commit()

    return {
        "assessment_id": assessment_id,
        "result": result,
    }


@router.get("/{assessment_id}/result")
def get_result(assessment_id: int, db: DBSession = Depends(get_db)):
    assessment = db.query(models.Assessment).filter_by(id=assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not assessment.result:
        raise HTTPException(status_code=400, detail="Assessment not yet evaluated")
    return {
        "assessment_id": assessment_id,
        "assessment_type": assessment.assessment_type,
        "status": assessment.status,
        "result": json.loads(assessment.result),
    }
