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

Your job is to score the candidate's answers. The system (not you) decides the final channel
based on your scores and the candidate's current state.

Channel thresholds (used by the system to decide final channel):
- foundation:  accuracy >= 60  AND fluency >= 50
- deepdive:    accuracy >= 75  AND depth >= 65  AND fluency >= 65
- simulation:  accuracy >= 85  AND depth >= 80  AND fluency >= 75

Pick the highest channel whose thresholds your scores support — this is your best guess
at the candidate's current competence. Do NOT output "improvement"; the system routes
candidates into improvement automatically based on thresholds.

Always populate "gaps" with the specific concept_tag values the candidate struggled with.
These drive targeted improvement sessions — empty or vague gaps hurt the candidate.

Level assignment:
- junior:  overall accuracy < 60
- mid:     overall accuracy 60-84
- senior:  overall accuracy >= 85

You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no extra text.

JSON format:
{
  "level": "junior|mid|senior",
  "channel": "foundation|deepdive|simulation",
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


_CHANNEL_THRESHOLDS = {
    "foundation": {"accuracy": 60, "depth": 0, "fluency": 50},
    "deepdive": {"accuracy": 75, "depth": 65, "fluency": 65},
    "simulation": {"accuracy": 85, "depth": 80, "fluency": 75},
}

# The channel an advancement test is trying to move the candidate INTO.
# simulation is terminal — a mock interview that passes keeps the candidate there.
_NEXT_CHANNEL = {
    "foundation": "deepdive",
    "deepdive": "simulation",
    "simulation": "simulation",
}


def _meets(scores: dict, target: str) -> bool:
    t = _CHANNEL_THRESHOLDS[target]
    return (
        scores.get("accuracy", 0) >= t["accuracy"]
        and scores.get("depth", 0) >= t["depth"]
        and scores.get("fluency", 0) >= t["fluency"]
    )


def _enforce_thresholds(
    result: dict,
    current_channel: str,
    assessment_type: str,
    pre_improvement_channel: str | None,
) -> dict:
    """
    Decide the final channel deterministically.

    preliminary_test: calibrate directly — pick the highest channel whose thresholds are met.
    topic_gate / mock_interview:
      - Target channel = next channel above the candidate's "home" channel.
        If currently in improvement, home = pre_improvement_channel.
      - If scores meet the target's threshold → advance to target.
      - Otherwise → route into improvement (no regression).

    Improvement is NEVER LLM-driven anymore. It is entered automatically whenever
    a candidate fails their advancement bar, so they retry with focus on gaps.
    """
    scores = result.get("scores", {})

    if assessment_type == "preliminary_test":
        if _meets(scores, "simulation"):
            result["channel"] = "simulation"
        elif _meets(scores, "deepdive"):
            result["channel"] = "deepdive"
        else:
            result["channel"] = "foundation"
        return result

    # topic_gate / mock_interview
    home = (
        pre_improvement_channel
        if current_channel == "improvement" and pre_improvement_channel
        else (current_channel or "foundation")
    )
    target = _NEXT_CHANNEL.get(home, "deepdive")

    if _meets(scores, target):
        result["channel"] = target
    else:
        result["channel"] = "improvement"

    return result


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
    current_channel = candidate_context.get("channel", "foundation") or "foundation"
    pre_improvement_channel = candidate_context.get("pre_improvement_channel")

    try:
        response = _client.chat.completions.create(
            model=_MODEL,
            max_tokens=1200,
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

        # Deterministically enforce channel thresholds — LLM scores, Python decides channel
        result = _enforce_thresholds(
            result, current_channel, assessment_type, pre_improvement_channel
        )

        # Derive level from accuracy score
        acc = result["scores"].get("accuracy", 0)
        result["level"] = "senior" if acc >= 85 else ("mid" if acc >= 60 else "junior")

        print(f"[evaluator] scores={result['scores']} → channel={result['channel']} level={result['level']}")
        return result

    except Exception as e:
        print(f"[evaluator] Error: {e}")
        # Safe fallback — keeps the candidate where they are
        return {
            "level": candidate_context.get("level", "mid") or "mid",
            "channel": current_channel,
            "gaps": candidate_context.get("gaps", []),
            "strengths": candidate_context.get("strengths", []),
            "scores": {"accuracy": 0, "fluency": 0, "depth": 0},
            "feedback": "We couldn't evaluate your answers right now. Please try again.",
        }
