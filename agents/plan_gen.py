"""
Plan Gen Agent — grok-3, non-streaming.

Called ONCE after the preliminary test is evaluated.
Creates a personalised candidate_plan that the Mentor Agent reads on every chat turn.
"""
import json
from agents.llm import client as _client, SMART_MODEL as _MODEL

_SYSTEM_PROMPT = """You are a learning path optimizer for a software engineering mentoring platform.

Given a candidate's preliminary evaluation, produce a JSON learning plan that personalizes their mentoring journey.

You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no extra text.

JSON format:
{
  "section_order": [section_id_int, ...],
  "concept_weights": {"concept_tag": float, ...},
  "pattern_weights": {"conceptual": float, "scenario": float, "problem_solving": float},
  "difficulty_start": {"concept_tag": "foundational|deepdive|interview_ready", ...}
}

Rules:
- section_order: put sections containing gap concepts first
- concept_weights: 2.0 for gap concepts, 1.0 for neutral, 0.5 for strengths (already mastered)
- pattern_weights: use 1.5 for pattern types that expose the candidate's weaknesses, 1.0 for others
- difficulty_start: gap concepts start at "foundational", strength concepts start one band higher, others at channel default"""


def generate_plan(
    candidate_level: str,
    candidate_channel: str,
    gaps: list[str],
    strengths: list[str],
    sections: list[dict],
) -> dict:
    """
    Generate a personalised learning plan.

    Args:
        candidate_level:   "junior" | "mid" | "senior"
        candidate_channel: "foundation" | "deepdive" | "simulation"
        gaps:              list of concept tags the candidate struggled with
        strengths:         list of concept tags the candidate did well on
        sections:          list of {"id": int, "name": str, "concepts": list[str]}

    Returns:
        dict with keys: section_order, concept_weights, pattern_weights, difficulty_start
    """
    sections_text = "\n".join(
        f"  Section {s['id']} — {s['name']}: concepts = {s['concepts']}"
        for s in sections
    )

    user_msg = (
        f"Candidate level: {candidate_level}\n"
        f"Assigned channel: {candidate_channel}\n"
        f"Gaps (struggled with): {gaps}\n"
        f"Strengths (did well on): {strengths}\n\n"
        f"Available sections:\n{sections_text}\n\n"
        "Generate the personalized learning plan."
    )

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        raw = response.choices[0].message.content.strip()
        plan = json.loads(raw)

        # Ensure all sections appear in section_order
        all_ids = [s["id"] for s in sections]
        ordered = plan.get("section_order", [])
        for sid in all_ids:
            if sid not in ordered:
                ordered.append(sid)
        plan["section_order"] = ordered

        plan.setdefault("concept_weights", {})
        plan.setdefault("pattern_weights", {"conceptual": 1.0, "scenario": 1.0, "problem_solving": 1.0})
        plan.setdefault("difficulty_start", {})

        return plan

    except Exception as e:
        print(f"[plan_gen] Error: {e}")
        return {
            "section_order": [s["id"] for s in sections],
            "concept_weights": {},
            "pattern_weights": {"conceptual": 1.0, "scenario": 1.0, "problem_solving": 1.0},
            "difficulty_start": {},
        }
