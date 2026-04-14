"""
Session router — the orchestrator.

Each chat turn:
  1. Fetch context (session, candidate, section, plan)
  2. Determine next question to focus on
  3. Call Mentor Agent → clean response + signal
  4. Record answer in DB (session_answers)
  5. Update topic gate (covered_concepts, answer_count)
  6. Update candidate question history
  7. Check if gate fires
  8. If gate fires → run Evaluator → update candidate channel
  9. Select next concept/question

Streaming note:
  The mentor agent collects the full response internally (streaming to Anthropic
  for efficiency) and returns the clean text to us. We then stream it to the
  frontend in a simple SSE-like format using a StreamingResponse.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
import models
from database import get_db, SessionLocal
import memory
from agents import mentor
from core import topic_gate, question_selector

router = APIRouter()


# ── Request schemas ──────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    candidate_id: int
    section_id: int


class ChatRequest(BaseModel):
    candidate_id: int
    message: str


class EndSessionRequest(BaseModel):
    candidate_id: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pick_next_concept(session: models.Session) -> str:
    """Return the first uncovered required concept, or the current one if all covered."""
    covered = set(json.loads(session.covered_concepts or "[]"))
    required = json.loads(session.required_concepts or "[]")
    for concept in required:
        if concept not in covered:
            return concept
    return required[0] if required else "general"



def _format_qa_for_evaluator(session_id: int, db: DBSession) -> list[dict]:
    answers = (
        db.query(models.SessionAnswer)
        .filter_by(session_id=session_id)
        .order_by(models.SessionAnswer.created_at)
        .all()
    )
    result = []
    for a in answers:
        question_text = ""
        if a.question_id:
            q = db.query(models.Question).filter_by(id=a.question_id).first()
            if q:
                question_text = q.text
        result.append(
            {
                "question": question_text or f"Discussion on {a.concept_tag}",
                "answer": a.candidate_answer or "",
                "concept_tag": a.concept_tag,
            }
        )
    return result


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("")
def create_session(body: CreateSessionRequest, db: DBSession = Depends(get_db)):
    candidate = db.query(models.Candidate).filter_by(id=body.candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.channel:
        raise HTTPException(
            status_code=400,
            detail="Candidate must complete the preliminary test before starting a session",
        )

    section = db.query(models.Section).filter_by(id=body.section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # For improvement channel: only require the gap concepts that belong to this section
    all_concepts = json.loads(section.concepts or "[]")
    if candidate.channel == "improvement":
        gaps = json.loads(candidate.gaps or "[]")
        required = [c for c in gaps if c in all_concepts]
        if not required:
            # No gaps in this section — fall back to all concepts
            required = all_concepts
    else:
        required = all_concepts

    session = models.Session(
        candidate_id=candidate.id,
        section_id=section.id,
        channel=candidate.channel,
        covered_concepts=json.dumps([]),
        required_concepts=json.dumps(required),
        answer_count=0,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Pick the first question
    band = question_selector.select_band(candidate.channel, last_quality=None)
    first_concept = required[0] if required else all_concepts[0]
    first_question = question_selector.fetch_question(
        db=db,
        candidate_id=candidate.id,
        session_id=session.id,
        concept_tag=first_concept,
        band=band,
        seniority=candidate.learning_path_id and "mid" or "mid",
    )

    session.current_concept_tag = first_concept
    db.commit()

    # Store the first question in memory so the chat loop reuses it
    first_q_dict = None
    if first_question:
        first_q_dict = {
            "id": first_question.id,
            "text": first_question.text,
            "concept_tag": first_question.concept_tag,
        }
        memory.set_current_question(session.id, first_q_dict)

    # Generate the mentor's opening message so the candidate doesn't have to go first
    opening = mentor.get_opening_message(
        channel=candidate.channel,
        candidate_level=candidate.level or "mid",
        section_name=section.name,
        first_concept_tag=first_concept,
        first_question_text=first_question.text if first_question else None,
        gaps=json.loads(candidate.gaps or "[]"),
    )
    memory.append_message(session.id, "assistant", opening)

    return {
        "session_id": session.id,
        "section": {"id": section.id, "name": section.name},
        "channel": candidate.channel,
        "required_concepts": required,
        "first_question": first_q_dict,
        "opening_message": opening,
    }


@router.post("/{session_id}/chat")
def chat(session_id: int, body: ChatRequest):
    """
    Main chat turn. Returns a StreamingResponse.

    The response body contains the mentor's text, followed by a JSON metadata block:
      [META]{...}[/META]

    The frontend reads this and uses the metadata to update UI state.
    """

    def generate():
        # Open a dedicated DB session for this streaming response
        db = SessionLocal()
        try:
            session = db.query(models.Session).filter_by(id=session_id).first()
            if not session or session.status != "active":
                yield "[ERROR]Session not found or already ended[/ERROR]"
                return

            candidate = db.query(models.Candidate).filter_by(id=body.candidate_id).first()
            if not candidate:
                yield "[ERROR]Candidate not found[/ERROR]"
                return

            section = db.query(models.Section).filter_by(id=session.section_id).first()

            # Determine last quality from previous answers in this session
            last_answer = (
                db.query(models.SessionAnswer)
                .filter_by(session_id=session_id)
                .order_by(models.SessionAnswer.created_at.desc())
                .first()
            )
            last_quality = last_answer.quality if last_answer else None

            # Reuse the in-memory current question so it doesn't jump around mid-concept.
            # Only fetch a fresh question when the concept has changed (covered → next concept).
            concept_tag = _pick_next_concept(session)
            cached_q = memory.get_current_question(session_id)

            if cached_q and cached_q.get("concept_tag") == concept_tag:
                # Same concept — keep asking about the same question
                question_text = cached_q["text"]
                question_id = cached_q["id"]
            else:
                # Concept changed — fetch a new question for the new concept
                band = question_selector.select_band(candidate.channel, last_quality)
                fetched = question_selector.fetch_question(
                    db=db,
                    candidate_id=candidate.id,
                    session_id=session_id,
                    concept_tag=concept_tag,
                    band=band,
                )
                if fetched:
                    cached_q = {"id": fetched.id, "text": fetched.text, "concept_tag": fetched.concept_tag}
                    memory.set_current_question(session_id, cached_q)
                    question_text = fetched.text
                    question_id = fetched.id
                else:
                    question_text = None
                    question_id = None

            # Get candidate plan context
            plan = None
            if candidate.plan_id:
                plan = db.query(models.CandidatePlan).filter_by(id=candidate.plan_id).first()

            # Call Mentor Agent (collects full response, then returns)
            clean_response, signal = mentor.stream_mentor_response(
                channel=candidate.channel,
                candidate_level=candidate.level or "mid",
                current_concept_tag=concept_tag,
                covered_concepts=json.loads(session.covered_concepts or "[]"),
                required_concepts=json.loads(session.required_concepts or "[]"),
                gaps=json.loads(candidate.gaps or "[]"),
                strengths=json.loads(candidate.strengths or "[]"),
                section_name=section.name if section else "",
                section_description=section.description if section else "",
                current_question_text=question_text,
                last_quality=last_quality,
                chat_history=memory.get_history(session_id),
                user_message=body.message,
            )

            # Extract concept_tag and quality from signal (fall back gracefully)
            sig_concept = concept_tag
            sig_quality = "partial"
            if signal:
                sig_concept = signal.get("concept_tag", concept_tag)
                sig_quality = signal.get("quality", "partial")

            # Update in-memory history
            memory.append_message(session_id, "user", body.message)
            memory.append_message(session_id, "assistant", clean_response)

            # Persist session answer
            db.add(
                models.SessionAnswer(
                    session_id=session_id,
                    question_id=question_id,
                    candidate_answer=body.message,
                    concept_tag=sig_concept,
                    quality=sig_quality,
                )
            )
            db.commit()

            # Update topic gate
            topic_gate.record_answer_signal(db, session_id, sig_concept, sig_quality)

            # Update candidate question history
            if question_id:
                question_selector.update_question_history(db, candidate.id, question_id, sig_quality)

            # Check if gate fires
            gate_fired = topic_gate.check_topic_gate(db, session_id)

            # When gate fires: create an advancement assessment for the candidate to take
            advancement_assessment_id = None  # set below if gate fires
            if gate_fired and session.status == "active":
                session.status = "ended"
                db.commit()

                # Build advancement test (one question per concept at next-level band)
                channel = candidate.channel or "foundation"
                CHANNEL_NEXT_BAND = {
                    "foundation": "deepdive",
                    "deepdive": "interview_ready",
                    "simulation": "interview_ready",
                    "improvement": "deepdive",
                }
                target_band = CHANNEL_NEXT_BAND.get(channel, "deepdive")

                concepts = json.loads(section.concepts or "[]") if section else []
                adv_question_ids = []
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
                        q = (
                            db.query(models.Question)
                            .filter_by(section_id=session.section_id, concept_tag=concept)
                            .first()
                        )
                    if q:
                        adv_question_ids.append(q.id)

                if adv_question_ids:
                    adv_assessment = models.Assessment(
                        candidate_id=candidate.id,
                        assessment_type="topic_gate",
                        session_id=session_id,
                        status="pending",
                        question_ids=json.dumps(adv_question_ids),
                    )
                    db.add(adv_assessment)
                    db.commit()
                    db.refresh(adv_assessment)
                    advancement_assessment_id = adv_assessment.id

            # Work out what question the frontend should show after this turn
            db.refresh(session)
            next_concept = _pick_next_concept(session)
            next_question = None
            if not gate_fired:
                current_cached = memory.get_current_question(session_id)
                if current_cached and current_cached.get("concept_tag") == next_concept:
                    # Still on the same concept — keep showing the same question
                    next_question = current_cached
                else:
                    # Concept advanced — fetch and cache a fresh question
                    next_band = question_selector.select_band(candidate.channel, sig_quality)
                    nq = question_selector.fetch_question(
                        db=db,
                        candidate_id=candidate.id,
                        session_id=session_id,
                        concept_tag=next_concept,
                        band=next_band,
                    )
                    if nq:
                        next_question = {"id": nq.id, "text": nq.text, "concept_tag": nq.concept_tag}
                        memory.set_current_question(session_id, next_question)
                        session.current_concept_tag = nq.concept_tag
                        db.commit()

            # Stream the mentor's response text to the client
            yield clean_response

            # Append metadata block for the frontend to parse
            meta = {
                "concept_tag": sig_concept,
                "quality": sig_quality,
                "gate_fired": gate_fired,
                "covered_concepts": json.loads(session.covered_concepts or "[]"),
                "required_concepts": json.loads(session.required_concepts or "[]"),
                "answer_count": session.answer_count,
                "next_question": next_question,
                "advancement_assessment_id": advancement_assessment_id,
            }
            yield f"\n[META]{json.dumps(meta)}[/META]"

        except Exception as e:
            print(f"[session/chat] Error: {e}")
            yield f"\n[ERROR]{str(e)}[/ERROR]"
        finally:
            db.close()

    return StreamingResponse(generate(), media_type="text/plain")


@router.get("/{session_id}/gate-status")
def gate_status(session_id: int, db: DBSession = Depends(get_db)):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    fired = topic_gate.check_topic_gate(db, session_id)
    return {
        "gate_fired": fired,
        "covered_concepts": json.loads(session.covered_concepts or "[]"),
        "required_concepts": json.loads(session.required_concepts or "[]"),
        "answer_count": session.answer_count,
        "status": session.status,
    }


@router.post("/{session_id}/end")
def end_session(session_id: int, body: EndSessionRequest, db: DBSession = Depends(get_db)):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "ended"
    db.commit()

    # Free in-memory state
    memory.clear_session(session_id)

    return {
        "session_id": session_id,
        "status": "ended",
        "summary": {
            "covered_concepts": json.loads(session.covered_concepts or "[]"),
            "required_concepts": json.loads(session.required_concepts or "[]"),
            "answer_count": session.answer_count,
        },
    }
