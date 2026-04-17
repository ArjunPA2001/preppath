"""
Pipeline (Feeder) router.

Lets an author build a learning path with sections and evaluation patterns,
then publish it — publishing triggers the Question Gen Agent to expand
each section's concepts into a full question bank and generate a rubric.

Endpoints:
  GET    /pipelines                          — list all learning paths
  POST   /pipelines                          — create a learning path (draft)
  GET    /pipelines/{id}                     — full path with sections & patterns
  POST   /pipelines/{id}/sections            — add a section
  POST   /sections/{section_id}/patterns     — add an eval pattern to a section
  POST   /pipelines/{id}/publish             — run Question Gen for every section
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db
from agents import question_gen

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────────────

class CreatePipelineRequest(BaseModel):
    name: str
    seniority: str = "mid"
    language: str = ""
    description: str = ""
    sample_questions: list[str] = []


class CreateSectionRequest(BaseModel):
    name: str
    description: str = ""
    concepts: list[str] = []
    sample_questions: list[str] = []


class CreatePatternRequest(BaseModel):
    name: str
    description: str = ""
    sample_patterns: list[str] = []


# ── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_path(lp: models.LearningPath, db: DBSession) -> dict:
    sections = (
        db.query(models.Section)
        .filter_by(learning_path_id=lp.id)
        .order_by(models.Section.order_index)
        .all()
    )
    sec_out = []
    for s in sections:
        patterns = (
            db.query(models.EvalPattern)
            .filter_by(section_id=s.id)
            .order_by(models.EvalPattern.order_index)
            .all()
        )
        sec_out.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "concepts": json.loads(s.concepts or "[]"),
            "rubric": s.rubric or "",
            "sample_questions": json.loads(s.sample_questions or "[]"),
            "patterns": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "sample_patterns": json.loads(p.sample_patterns or "[]"),
                }
                for p in patterns
            ],
        })
    return {
        "id": lp.id,
        "name": lp.name,
        "description": lp.description or "",
        "seniority": lp.seniority,
        "language": lp.language or "",
        "sample_questions": json.loads(lp.sample_questions or "[]"),
        "status": lp.status or "draft",
        "sections": sec_out,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
def list_pipelines(db: DBSession = Depends(get_db)):
    paths = db.query(models.LearningPath).order_by(models.LearningPath.id).all()
    return {
        "pipelines": [
            {
                "id": p.id,
                "name": p.name,
                "seniority": p.seniority,
                "language": p.language or "",
                "status": p.status or "draft",
            }
            for p in paths
        ]
    }


@router.post("")
def create_pipeline(body: CreatePipelineRequest, db: DBSession = Depends(get_db)):
    lp = models.LearningPath(
        name=body.name,
        description=body.description,
        seniority=body.seniority,
        language=body.language,
        sample_questions=json.dumps(body.sample_questions),
        status="draft",
    )
    db.add(lp)
    db.commit()
    db.refresh(lp)
    return {"id": lp.id, "name": lp.name, "status": lp.status}


@router.get("/{pipeline_id}")
def get_pipeline(pipeline_id: int, db: DBSession = Depends(get_db)):
    lp = db.query(models.LearningPath).filter_by(id=pipeline_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return _serialize_path(lp, db)


@router.post("/{pipeline_id}/sections")
def add_section(pipeline_id: int, body: CreateSectionRequest, db: DBSession = Depends(get_db)):
    lp = db.query(models.LearningPath).filter_by(id=pipeline_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    existing_count = db.query(models.Section).filter_by(learning_path_id=pipeline_id).count()
    sec = models.Section(
        learning_path_id=pipeline_id,
        name=body.name,
        description=body.description,
        order_index=existing_count,
        concepts=json.dumps(body.concepts),
        sample_questions=json.dumps(body.sample_questions),
    )
    db.add(sec)
    db.commit()
    db.refresh(sec)
    return {"id": sec.id, "name": sec.name, "order_index": sec.order_index}


@router.put("/sections/{section_id}")
def update_section(section_id: int, body: CreateSectionRequest, db: DBSession = Depends(get_db)):
    """Update a section's name, description, concepts, and sample questions."""
    sec = db.query(models.Section).filter_by(id=section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    sec.name = body.name
    sec.description = body.description
    sec.concepts = json.dumps(body.concepts)
    sec.sample_questions = json.dumps(body.sample_questions)
    db.commit()
    db.refresh(sec)
    return {"id": sec.id, "name": sec.name}


@router.post("/sections/{section_id}/patterns")
def add_pattern(section_id: int, body: CreatePatternRequest, db: DBSession = Depends(get_db)):
    sec = db.query(models.Section).filter_by(id=section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")

    existing_count = db.query(models.EvalPattern).filter_by(section_id=section_id).count()
    pat = models.EvalPattern(
        section_id=section_id,
        name=body.name,
        description=body.description,
        sample_patterns=json.dumps(body.sample_patterns),
        order_index=existing_count,
    )
    db.add(pat)
    db.commit()
    db.refresh(pat)
    return {"id": pat.id, "name": pat.name}


@router.post("/{pipeline_id}/publish")
def publish_pipeline(pipeline_id: int, db: DBSession = Depends(get_db)):
    """
    Runs the Question Gen Agent on every section. For each section:
      - Expands each concept into 9 questions (3 bands × 3 types)
      - Generates the section rubric
    Marks the path as 'published' when done.
    """
    lp = db.query(models.LearningPath).filter_by(id=pipeline_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    sections = db.query(models.Section).filter_by(learning_path_id=pipeline_id).all()
    if not sections:
        raise HTTPException(status_code=400, detail="Pipeline has no sections")

    summaries = []
    for sec in sections:
        summary = question_gen.generate_for_section(db, sec)
        summaries.append(summary)

    lp.status = "published"
    db.commit()

    return {
        "pipeline_id": pipeline_id,
        "status": "published",
        "sections": summaries,
    }
