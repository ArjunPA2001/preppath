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
    sample_examples: list[str] | None = None,
) -> str:
    existing_block = (
        "Existing questions to avoid duplicating:\n" +
        "\n".join(f"  - {t}" for t in existing_texts)
        if existing_texts
        else "No existing questions yet."
    )

    examples_block = ""
    if sample_examples:
        examples_block = (
            "\nStyle examples (questions provided by the domain expert — "
            "match their phrasing style, depth, and domain vocabulary):\n" +
            "\n".join(f"  - {t}" for t in sample_examples) +
            "\n"
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
{examples_block}
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


_TAG_SYSTEM = """You are an expert technical question classifier for a software engineering mentoring platform.

Your job is to tag raw question strings with structured metadata so they can be stored in a question bank.

You MUST respond with ONLY a valid JSON array. No markdown, no explanation, no extra text."""


def tag_and_save_samples(
    db: DBSession,
    section: models.Section,
    sample_texts: list[str],
    seniority: str = "mid",
) -> list[str]:
    """
    Tag a list of raw sample question strings with concept_tag, difficulty_band,
    pattern_type, and seniority using the LLM, then save them to the questions table.

    Returns the list of sample question texts (even ones that failed tagging) so
    they can be passed as style examples to generate_for_concept().
    """
    if not sample_texts:
        return []

    concepts = json.loads(section.concepts or "[]")
    if not concepts:
        print(f"  [question_gen] No concepts on section {section.id} — skipping sample tagging")
        return sample_texts

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(sample_texts))

    prompt = f"""Tag the following sample questions for the learning section below.

Section: {section.name}
Description: {section.description or ""}
Valid concept_tags (pick EXACTLY one from this list per question): {concepts}
Seniority level: {seniority}

Rules:
- concept_tag: MUST be one of the listed valid tags
- difficulty_band: "foundational" | "deepdive" | "interview_ready"
- pattern_type: "conceptual" | "scenario" | "problem_solving"
- Preserve the original question text exactly

Sample questions to tag:
{numbered}

Return ONLY a JSON array with one object per question:
[
  {{
    "text": "exact original question text",
    "concept_tag": "one_from_valid_list",
    "difficulty_band": "foundational|deepdive|interview_ready",
    "pattern_type": "conceptual|scenario|problem_solving"
  }}
]"""

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": _TAG_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        tagged = json.loads(raw)
    except Exception as e:
        print(f"  [question_gen] Sample tagging failed for section {section.id}: {e}")
        return sample_texts  # still return texts for style examples

    added = 0
    for q in tagged:
        concept_tag = q.get("concept_tag", "")
        band = q.get("difficulty_band", "")
        ptype = q.get("pattern_type", "")
        text = q.get("text", "").strip()

        if not text or concept_tag not in concepts or not band or not ptype:
            continue

        # Avoid inserting a duplicate of an already-existing question
        exists = (
            db.query(models.Question)
            .filter_by(section_id=section.id, concept_tag=concept_tag, text=text)
            .first()
        )
        if exists:
            continue

        # Determine is_preliminary: first foundational+conceptual per concept gets the flag
        has_prelim = (
            db.query(models.Question)
            .filter_by(section_id=section.id, concept_tag=concept_tag, is_preliminary=True)
            .first()
            is not None
        )
        is_prelim = (not has_prelim) and band == "foundational" and ptype == "conceptual"

        db.add(
            models.Question(
                section_id=section.id,
                concept_tag=concept_tag,
                text=text,
                difficulty_band=band,
                pattern_type=ptype,
                seniority=seniority,
                is_preliminary=is_prelim,
            )
        )
        added += 1

    if added:
        db.commit()
        print(f"  [question_gen] section {section.id}: saved {added} sample questions")

    return sample_texts  # return originals as style examples


_RUBRIC_SYSTEM = """You are an expert evaluator for a software engineering mentoring platform.

Write a concise evaluation rubric for a section. The rubric will be read by an AI evaluator to grade candidate answers.

You MUST respond with ONLY plain text — no JSON, no markdown headers."""


def generate_for_concept(
    db: DBSession,
    concept_tag: str,
    section: models.Section,
    seniority: str = "mid",
    sample_examples: list[str] | None = None,
) -> int:
    """
    Generate 9 questions for a concept and save them to the DB.
    Skips combinations that already exist to avoid duplication.

    sample_examples: optional list of question texts (from the feeder's sample
    questions) passed to the LLM as style guidance.

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
        sample_examples=sample_examples or [],
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

        # Deterministically mark the foundational+conceptual question as preliminary.
        # Do NOT trust the LLM flag — it is unreliable. We own this decision.
        is_prelim = (
            not has_preliminary
            and band == "foundational"
            and ptype == "conceptual"
        )
        if is_prelim:
            has_preliminary = True

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

    # Safety net: if we added questions but still have no preliminary question
    # (e.g. LLM skipped foundational+conceptual), mark the first foundational question.
    if added and not has_preliminary:
        first_foundational = (
            db.query(models.Question)
            .filter_by(
                concept_tag=concept_tag,
                section_id=section.id,
                difficulty_band="foundational",
            )
            .first()
        )
        if first_foundational:
            first_foundational.is_preliminary = True
            has_preliminary = True

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

    Order of operations:
      1. Tag and save sample questions (feeder-provided) — they become real DB
         questions and serve as style examples for the generator.
      2. Generate 9 questions per concept, passing sample texts as style hints.
      3. (Re)generate the section rubric.

    Returns a summary dict.
    """
    concepts = json.loads(section.concepts or "[]")
    seniority = "mid"

    lp = db.query(models.LearningPath).filter_by(id=section.learning_path_id).first()
    if lp:
        seniority = lp.seniority

    # Step 1: tag and persist sample questions; get back the texts as style examples
    raw_samples = json.loads(section.sample_questions or "[]")
    sample_examples = tag_and_save_samples(db, section, raw_samples, seniority)

    # Step 2: generate the full question bank, guided by the sample style
    total_added = 0
    for concept in concepts:
        added = generate_for_concept(db, concept, section, seniority, sample_examples)
        total_added += added

    # Step 3: (re)generate rubric
    rubric = generate_rubric(section.name, section.description or "", concepts, seniority)
    section.rubric = rubric
    db.commit()

    return {
        "section_id": section.id,
        "concepts": concepts,
        "samples_processed": len(raw_samples),
        "questions_added": total_added,
    }
