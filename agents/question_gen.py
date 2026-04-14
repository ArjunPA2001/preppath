"""
Question Generation Agent — uses SMART_MODEL (grok-3).

Two entry points:

  generate_for_concept(db, concept_tag, section, seniority)
    Called during seeding AND by the question selector when a candidate's pool
    runs dry mid-session. Generates 9 questions (3 bands × 3 types) and writes
    them directly to the DB. Returns the number of questions added.

  generate_rubric(section_name, section_description, concepts, seniority)
    Called during seeding to produce the evaluation rubric for a section.
    Returns a plain-text rubric string (not saved here — caller saves it).

Band × Type grid produced per concept:
  bands:  foundational · deepdive · interview_ready
  types:  conceptual   · scenario  · problem_solving
  total:  9 questions per concept

One question is marked is_preliminary=True:
  foundational + conceptual — used for the cold-start preliminary test.
  Skipped if a preliminary question already exists for that concept.
"""
import json
import models
from sqlalchemy.orm import Session as DBSession
from agents.llm import client as _client, SMART_MODEL as _MODEL

BANDS = ["foundational", "deepdive", "interview_ready"]
TYPES = ["conceptual", "scenario", "problem_solving"]

_QUESTION_SYSTEM = """You are an expert technical question writer for a software engineering mentoring platform.

Your job is to generate interview and learning questions that are precise, unambiguous, and appropriately challenging.

Band definitions:
- foundational: tests core definitions and basic understanding. Suitable for someone learning the topic.
- deepdive: tests trade-offs, internals, edge cases, and "why" reasoning. Expects working knowledge.
- interview_ready: tests system design thinking, architectural decisions, and real-world judgment under constraints.

Type definitions:
- conceptual: asks the candidate to explain, define, or compare ("What is X?", "Explain the difference between X and Y")
- scenario: presents a concrete real-world situation to reason through ("You are building X and encounter Y — how do you approach it?")
- problem_solving: asks the candidate to design, architect, or evaluate ("Design X for production", "Compare approaches A vs B for use case C")

You MUST respond with ONLY a valid JSON array. No markdown, no explanation, no extra text."""


def _build_generation_prompt(
    concept_tag: str,
    section_name: str,
    section_description: str,
    seniority: str,
    existing_texts: list[str],
    needs_preliminary: bool,
) -> str:
    existing_block = (
        "Existing questions to avoid duplicating:\n" +
        "\n".join(f"  - {t}" for t in existing_texts)
        if existing_texts
        else "No existing questions yet."
    )

    preliminary_note = (
        'Mark is_preliminary=true on exactly ONE question: the foundational + conceptual combination.'
        if needs_preliminary
        else 'Set is_preliminary=false on ALL questions (a preliminary question already exists for this concept).'
    )

    return f"""Generate 9 unique technical questions for the concept "{concept_tag}" at {seniority} level.

Section: {section_name}
Context: {section_description}

Generate exactly 9 questions — one for EACH combination of the 3 bands × 3 types:
  bands: foundational, deepdive, interview_ready
  types: conceptual, scenario, problem_solving

{existing_block}

{preliminary_note}

Return ONLY a JSON array with exactly 9 objects:
[
  {{
    "concept_tag": "{concept_tag}",
    "text": "full question text here",
    "difficulty_band": "foundational|deepdive|interview_ready",
    "pattern_type": "conceptual|scenario|problem_solving",
    "seniority": "{seniority}",
    "is_preliminary": false
  }}
]"""


_RUBRIC_SYSTEM = """You are an expert evaluator for a software engineering mentoring platform.

Write a concise evaluation rubric for a section. The rubric will be read by an AI evaluator to grade candidate answers.

You MUST respond with ONLY plain text — no JSON, no markdown headers."""


def generate_for_concept(
    db: DBSession,
    concept_tag: str,
    section: models.Section,
    seniority: str = "mid",
) -> int:
    """
    Generate 9 questions for a concept and save them to the DB.
    Skips combinations that already exist to avoid duplication.
    Returns the number of new questions added.
    """
    # Gather existing questions for this concept (for dedup context)
    existing = (
        db.query(models.Question)
        .filter_by(concept_tag=concept_tag, section_id=section.id)
        .all()
    )
    existing_texts = [q.text for q in existing]
    existing_combos = {(q.difficulty_band, q.pattern_type) for q in existing}

    # Check if a preliminary question already exists for this concept
    has_preliminary = any(q.is_preliminary for q in existing)

    # If all 9 combos already exist, nothing to do
    all_combos = {(b, t) for b in BANDS for t in TYPES}
    missing_combos = all_combos - existing_combos
    if not missing_combos:
        print(f"  [question_gen] {concept_tag}: all 9 variants exist, skipping")
        return 0

    prompt = _build_generation_prompt(
        concept_tag=concept_tag,
        section_name=section.name,
        section_description=section.description or "",
        seniority=seniority,
        existing_texts=existing_texts,
        needs_preliminary=not has_preliminary,
    )

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": _QUESTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        questions = json.loads(raw)

    except Exception as e:
        print(f"  [question_gen] Failed for {concept_tag}: {e}")
        return 0

    added = 0
    for q in questions:
        band = q.get("difficulty_band")
        ptype = q.get("pattern_type")
        text = q.get("text", "").strip()

        if not text or not band or not ptype:
            continue

        # Skip combinations that already exist
        if (band, ptype) in existing_combos:
            continue

        # Ensure only one preliminary per concept across the whole DB
        is_prelim = bool(q.get("is_preliminary")) and not has_preliminary
        if is_prelim:
            has_preliminary = True  # only flag the first one

        db.add(
            models.Question(
                section_id=section.id,
                concept_tag=concept_tag,
                text=text,
                difficulty_band=band,
                pattern_type=ptype,
                seniority=q.get("seniority", seniority),
                is_preliminary=is_prelim,
            )
        )
        existing_combos.add((band, ptype))
        added += 1

    if added:
        db.commit()
        print(f"  [question_gen] {concept_tag}: added {added} questions")

    return added


def generate_rubric(
    section_name: str,
    section_description: str,
    concepts: list[str],
    seniority: str = "mid",
) -> str:
    """
    Generate an evaluation rubric for a section.
    Returns plain text — caller is responsible for saving it.
    """
    prompt = (
        f"Write an evaluation rubric for the section '{section_name}' at {seniority} level.\n"
        f"Section description: {section_description}\n"
        f"Concepts covered: {', '.join(concepts)}\n\n"
        "The rubric must specify how to score candidates on three dimensions (0-100 each):\n"
        "  accuracy  — technical correctness\n"
        "  depth     — reasoning, trade-offs, edge cases\n"
        "  fluency   — clarity and structure of explanation\n\n"
        "Keep it concise (under 200 words). It will be read by an AI evaluator."
    )

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": _RUBRIC_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [question_gen] Rubric generation failed for {section_name}: {e}")
        return (
            f"Evaluate on accuracy (technical correctness), "
            f"depth (trade-offs and edge cases), and fluency (clarity). "
            f"Concepts in scope: {', '.join(concepts)}."
        )


def generate_for_section(db: DBSession, section: models.Section) -> dict:
    """
    Convenience wrapper: generate questions for ALL concepts in a section
    and (re)generate the rubric. Updates section.rubric in the DB.
    Returns a summary dict.
    """
    concepts = json.loads(section.concepts or "[]")
    seniority = "mid"  # could be pulled from the learning path if needed

    # Try to get seniority from the learning path
    from sqlalchemy.orm import Session as DBSession  # avoid circular at module level
    lp = db.query(models.LearningPath).filter_by(id=section.learning_path_id).first()
    if lp:
        seniority = lp.seniority

    total_added = 0
    for concept in concepts:
        added = generate_for_concept(db, concept, section, seniority)
        total_added += added

    # Regenerate rubric
    rubric = generate_rubric(section.name, section.description or "", concepts, seniority)
    section.rubric = rubric
    db.commit()

    return {"section_id": section.id, "concepts": concepts, "questions_added": total_added}
