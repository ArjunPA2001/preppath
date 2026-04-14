"""
Evaluator Agent — grok-3-mini, fast and non-streaming.

Handles all three evaluation triggers with the same agent:
  - preliminary_test  → sets initial channel, level, gaps, strengths
  - topic_gate        → evaluates session answers, may advance channel
  - mock_interview    → evaluates full simulation session

Channel assignment thresholds (from architecture):
  foundation:  accuracy >= 60, fluency >= 50
  deepdive:    accuracy >= 75, depth >= 65, fluency >= 65
  simulation:  accuracy >= 85, depth >= 80, fluency >= 75
  improvement: evaluator decides when a concept cluster is critically weak

Returns a dict — NEVER writes to the DB directly. Caller handles persistence.
"""
import json
from agents.llm import client as _client, FAST_MODEL as _MODEL

_SYSTEM_PROMPT = """You are a strict but fair technical evaluator for a software engineering mentoring platform.

Your job is to evaluate a candidate's answers and assign them to the right learning channel.

Channel thresholds:
- foundation:  accuracy >= 60  AND fluency >= 50   (needs foundational teaching)
- deepdive:    accuracy >= 75  AND depth >= 65  AND fluency >= 65  (ready for depth)
- simulation:  accuracy >= 85  AND depth >= 80  AND fluency >= 75  (interview-ready)
- improvement: assign when specific concept clusters are critically weak (accuracy < 50 for that concept)
               even if overall scores are decent — improvement is a temporary detour

Level assignment:
- junior:  overall accuracy < 60
- mid:     overall accuracy 60-84
- senior:  overall accuracy >= 85

You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no extra text.

JSON format:
{
  "level": "junior|mid|senior",
  "channel": "foundation|deepdive|simulation|improvement",
  "gaps": ["concept_tag", ...],
  "strengths": ["concept_tag", ...],
  "scores": {"accuracy": 0-100, "fluency": 0-100, "depth": 0-100},
  "feedback": "two or three sentences of constructive, actionable feedback"
}"""


def _build_user_message(
    assessment_type: str,
    qa_pairs: list[dict],
    candidate_context: dict,
    rubric: str,
) -> str:
    lines = [
        f"Assessment type: {assessment_type}",
        f"Candidate level (current): {candidate_context.get('level', 'unknown')}",
        f"Current channel: {candidate_context.get('channel', 'none')}",
        f"Known gaps: {', '.join(candidate_context.get('gaps', [])) or 'none'}",
        f"Known strengths: {', '.join(candidate_context.get('strengths', [])) or 'none'}",
        "",
        "Rubric:",
        rubric,
        "",
        "Candidate Q&A:",
    ]

    for i, pair in enumerate(qa_pairs, 1):
        lines.append(f"\nQ{i} [{pair['concept_tag']}]: {pair['question']}")
        lines.append(f"A{i}: {pair['answer'] or '(no answer given)'}")

    return "\n".join(lines)


def evaluate(
    assessment_type: str,
    qa_pairs: list[dict],
    candidate_context: dict,
    rubric: str,
) -> dict:
    """
    Evaluate a set of Q&A pairs and return a structured result dict.

    Args:
        assessment_type: "preliminary_test" | "topic_gate" | "mock_interview"
        qa_pairs: list of {"question": str, "answer": str, "concept_tag": str}
        candidate_context: {"level": str, "channel": str, "gaps": list, "strengths": list}
        rubric: free-text rubric for the section being evaluated

    Returns:
        dict with keys: level, channel, gaps, strengths, scores, feedback
    """
    user_msg = _build_user_message(assessment_type, qa_pairs, candidate_context, rubric)

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
        result = json.loads(raw)

        # Validate required keys
        result.setdefault("level", "mid")
        result.setdefault("channel", "foundation")
        result.setdefault("gaps", [])
        result.setdefault("strengths", [])
        result.setdefault("scores", {"accuracy": 0, "fluency": 0, "depth": 0})
        result.setdefault("feedback", "Evaluation complete.")

        return result

    except Exception as e:
        print(f"[evaluator] Error: {e}")
        # Safe fallback — keeps the candidate where they are
        return {
            "level": candidate_context.get("level", "mid") or "mid",
            "channel": candidate_context.get("channel", "foundation") or "foundation",
            "gaps": candidate_context.get("gaps", []),
            "strengths": candidate_context.get("strengths", []),
            "scores": {"accuracy": 0, "fluency": 0, "depth": 0},
            "feedback": "We couldn't evaluate your answers right now. Please try again.",
        }
