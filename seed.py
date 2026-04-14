"""
Seed the database with one learning path, two sections, and one candidate.
Idempotent — safe to call on every startup.

Question seeding strategy:
  1. Insert hardcoded base questions (3 per concept) — these are the reliable foundation
     and guarantee the system works even if the LLM call fails.
  2. Call the Question Gen Agent to expand each concept to a full 9-question set
     (3 bands × 3 types). This runs once on first startup and is skipped on restarts.
"""
import json
from sqlalchemy.orm import Session
import models


# ── Question bank ────────────────────────────────────────────────────────────

SECTION_1_QUESTIONS = [
    # python_types
    {
        "concept_tag": "python_types",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "Explain the difference between mutable and immutable types in Python. Give two examples of each.",
    },
    {
        "concept_tag": "python_types",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "You have a function that receives 50,000 records and needs to deduplicate them quickly. "
            "Which Python data structures would you choose and why? What are the time complexity trade-offs?"
        ),
    },
    {
        "concept_tag": "python_types",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "Given Python's dynamic typing, how would you design a type-safe configuration system for a "
            "production application? Compare TypedDict, dataclasses, and Pydantic — when do you choose each?"
        ),
    },
    # python_functions
    {
        "concept_tag": "python_functions",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "What is the difference between *args and **kwargs in Python? When would you use each?",
    },
    {
        "concept_tag": "python_functions",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "You need to implement a retry mechanism for API calls with exponential backoff. "
            "Design this as a Python decorator. What edge cases must you handle?"
        ),
    },
    {
        "concept_tag": "python_functions",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "Explain Python's closure mechanism and how it relates to the decorator pattern. "
            "What memory implications should you be aware of in long-running services?"
        ),
    },
    # python_oop
    {
        "concept_tag": "python_oop",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "What is the difference between __init__ and __new__ in a Python class? When would you override __new__?",
    },
    {
        "concept_tag": "python_oop",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "Design a plugin system using Python's abstract base classes (ABCs). "
            "How would you enforce interface contracts and allow third-party plugins to register themselves?"
        ),
    },
    {
        "concept_tag": "python_oop",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "Compare composition vs inheritance in Python. When would you use mixins, "
            "and what are their limitations in a large codebase with multiple inheritance?"
        ),
    },
]

SECTION_2_QUESTIONS = [
    # http_basics
    {
        "concept_tag": "http_basics",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "What are the main differences between GET, POST, PUT, and DELETE HTTP methods? Give a real-world example for each.",
    },
    {
        "concept_tag": "http_basics",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "A client is reporting intermittent 502 errors on your API. "
            "Walk through the HTTP-level diagnostics you would perform, from the client to the server."
        ),
    },
    {
        "concept_tag": "http_basics",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "Explain idempotency in HTTP methods and why it matters. "
            "How does this affect your API design and error-handling strategy when clients retry failed requests?"
        ),
    },
    # rest_api_design
    {
        "concept_tag": "rest_api_design",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "What makes an API RESTful? Name the key constraints of REST architecture.",
    },
    {
        "concept_tag": "rest_api_design",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "Design the REST endpoints for a task management system with users, projects, and tasks. "
            "Show the URL structure, HTTP methods, and response shapes for the main operations."
        ),
    },
    {
        "concept_tag": "rest_api_design",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "You're asked to review an existing API where every operation uses POST. "
            "What specific issues does this cause? How would you migrate to REST without breaking existing clients?"
        ),
    },
    # fastapi_routing
    {
        "concept_tag": "fastapi_routing",
        "difficulty_band": "foundational",
        "pattern_type": "conceptual",
        "is_preliminary": True,
        "text": "What is the difference between a path parameter and a query parameter in FastAPI? Give a code example of each.",
    },
    {
        "concept_tag": "fastapi_routing",
        "difficulty_band": "deepdive",
        "pattern_type": "scenario",
        "is_preliminary": False,
        "text": (
            "You need to add rate limiting to specific FastAPI routes without modifying each route handler. "
            "How would you use FastAPI's dependency injection system to implement this cleanly?"
        ),
    },
    {
        "concept_tag": "fastapi_routing",
        "difficulty_band": "interview_ready",
        "pattern_type": "problem_solving",
        "is_preliminary": False,
        "text": (
            "Explain FastAPI's async request handling model. When should you use async def vs def for route handlers, "
            "and what are the pitfalls of mixing blocking and async code in the same application?"
        ),
    },
]

SECTION_1_RUBRIC = """
Evaluate on three dimensions (0-100 each):

accuracy: Is the answer technically correct? Award full marks for correct facts, partial for mostly correct with minor errors, low marks for fundamental misunderstandings.

depth: Does the candidate go beyond surface knowledge? Look for: explaining the "why", discussing trade-offs, mentioning edge cases, comparing alternatives.

fluency: Is the answer well-structured and clearly communicated? Look for logical flow, appropriate technical vocabulary, and concise explanations without rambling.

Concepts in scope: python_types (mutable/immutable, type system), python_functions (args/kwargs, closures, decorators), python_oop (classes, inheritance, ABC, mixins).
"""

SECTION_2_RUBRIC = """
Evaluate on three dimensions (0-100 each):

accuracy: Is the answer technically correct? Award full marks for correct HTTP semantics and REST principles, partial for mostly right with gaps, low marks for fundamental misunderstandings.

depth: Does the candidate show practical knowledge? Look for: discussing real-world implications, mentioning edge cases (idempotency, status codes, versioning), comparing design choices.

fluency: Is the answer well-structured? Look for logical flow, correct use of HTTP/REST terminology, concise but complete explanations.

Concepts in scope: http_basics (methods, status codes, idempotency), rest_api_design (constraints, resource naming, versioning), fastapi_routing (path params, dependency injection, async handling).
"""


# ── Seed function ────────────────────────────────────────────────────────────

def run_seed(db: Session) -> None:
    # Idempotency guard
    if db.query(models.LearningPath).count() > 0:
        return

    # Learning path
    path = models.LearningPath(
        name="Python Backend Development",
        description="A comprehensive path covering Python fundamentals and building production-ready REST APIs with FastAPI.",
        seniority="mid",
    )
    db.add(path)
    db.flush()  # get path.id without full commit

    # Section 1
    sec1 = models.Section(
        learning_path_id=path.id,
        name="Python Fundamentals",
        description=(
            "Core Python concepts including the type system, function design patterns, "
            "and object-oriented programming. These are the building blocks everything else rests on."
        ),
        order_index=1,
        concepts=json.dumps(["python_types", "python_functions", "python_oop"]),
        rubric=SECTION_1_RUBRIC,
    )
    db.add(sec1)
    db.flush()

    for q in SECTION_1_QUESTIONS:
        db.add(models.Question(section_id=sec1.id, seniority="mid", **q))

    # Section 2
    sec2 = models.Section(
        learning_path_id=path.id,
        name="FastAPI Web Development",
        description=(
            "Building REST APIs with FastAPI — from HTTP fundamentals to API design principles "
            "to FastAPI-specific patterns like dependency injection and async routing."
        ),
        order_index=2,
        concepts=json.dumps(["http_basics", "rest_api_design", "fastapi_routing"]),
        rubric=SECTION_2_RUBRIC,
    )
    db.add(sec2)
    db.flush()

    for q in SECTION_2_QUESTIONS:
        db.add(models.Question(section_id=sec2.id, seniority="mid", **q))

    # Candidate
    candidate = models.Candidate(
        name="Alex Chen",
        email="alex@example.com",
        learning_path_id=path.id,
        channel="",   # set after preliminary test
        level="",     # set after preliminary test
        gaps=json.dumps([]),
        strengths=json.dumps([]),
    )
    db.add(candidate)

    db.commit()
    print("✓ Database seeded: 1 learning path, 2 sections, 18 base questions, 1 candidate")

    # ── Expand question pool with the Question Gen Agent ─────────────────────
    # Generates 9 variants per concept (3 bands × 3 types).
    # Skips combos that already exist so re-runs are safe.
    print("Expanding question pool via Question Gen Agent…")
    try:
        from agents import question_gen
        for section in [sec1, sec2]:
            print(f"  Generating for section: {section.name}")
            result = question_gen.generate_for_section(db, section)
            print(f"  → Added {result['questions_added']} questions, rubric updated")
        print("✓ Question pool expanded")
    except Exception as e:
        print(f"⚠ Question gen failed (base questions still available): {e}")
