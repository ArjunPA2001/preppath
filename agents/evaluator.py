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


_CHANNEL_ORDER = ["foundation", "deepdive", "simulation"]


def _enforce_thresholds(result: dict, current_channel: str, assessment_type: str) -> dict:
    """
    Override the LLM's channel suggestion with a deterministic score-based decision.

    Thresholds (from SDD §7):
      simulation:  accuracy >= 85, depth >= 80, fluency >= 75
      deepdive:    accuracy >= 75, depth >= 65, fluency >= 65
      foundation:  accuracy >= 60,              fluency >= 50
      improvement: any concept cluster critically weak (LLM flags this)
      regression:  deepdive → foundation if accuracy < 55
                   simulation → deepdive on significant regression (accuracy < 70 or depth < 65)

    For topic_gate / mock_interview: cap advancement at one step per session.
    For preliminary_test: free to assign any channel directly.
    """
    scores = result.get("scores", {})
    acc = scores.get("accuracy", 0)
    dep = scores.get("depth", 0)
    flu = scores.get("fluency", 0)
    llm_channel = result.get("channel", "foundation")

    # Compute score-based target channel
    if acc >= 85 and dep >= 80 and flu >= 75:
        score_channel = "simulation"
    elif acc >= 75 and dep >= 65 and flu >= 65:
        score_channel = "deepdive"
    elif acc >= 60 and flu >= 50:
        score_channel = "foundation"
    else:
        # Below foundation threshold
        score_channel = "foundation"

    # Improvement is a concept-level detour — respect LLM's call
    # (LLM has per-answer context we don't have here)
    if llm_channel == "improvement" and result.get("gaps"):
        result["channel"] = "improvement"
        return result

    # Apply regression for topic_gate / mock_interview
    if assessment_type in ("topic_gate", "mock_interview"):
        if current_channel == "deepdive" and acc < 55:
            result["channel"] = "foundation"
            return result
        if current_channel == "simulation" and (acc < 70 or dep < 65):
            result["channel"] = "deepdive"
            return result

        # Cap advancement at one step per session
        if current_channel in _CHANNEL_ORDER and score_channel in _CHANNEL_ORDER:
            curr_idx = _CHANNEL_ORDER.index(current_channel)
            tgt_idx = _CHANNEL_ORDER.index(score_channel)
            if tgt_idx > curr_idx + 1:
                score_channel = _CHANNEL_ORDER[curr_idx + 1]
            # Never regress more than one step
            if tgt_idx < curr_idx - 1:
                score_channel = _CHANNEL_ORDER[curr_idx - 1]

    result["channel"] = score_channel
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
        result = _enforce_thresholds(result, current_channel, assessment_type)

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
