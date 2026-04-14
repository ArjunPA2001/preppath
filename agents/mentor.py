"""
Mentor Agent — grok-3, streaming.

Called on every chat turn from the session router.
Adapts its persona and teaching technique based on the candidate's current channel.

Signal tag protocol:
  The agent appends <signal>{"concept_tag":"...","quality":"wrong|partial|correct"}</signal>
  to the END of every response. The router strips this before sending to the client.
"""
import json
import re
from agents.llm import client as _client, SMART_MODEL as _MODEL

# ── Channel personas ─────────────────────────────────────────────────────────

_PERSONAS = {
    "foundation": (
        "a patient and encouraging teacher. Your goal is concept coverage and basic correctness. "
        "Use simple language, concrete examples, and analogies. Always explain the 'why'. "
        "No time pressure. Scaffold the candidate's understanding step by step."
    ),
    "deepdive": (
        "a challenging senior engineer who pushes candidates to think deeper. "
        "Ask follow-up questions about trade-offs, edge cases, and design decisions. "
        "Don't accept surface answers — use the Socratic method to draw out reasoning."
    ),
    "simulation": (
        "a technical interviewer conducting a real interview. Be professional and neutral. "
        "Do NOT give hints. Apply time awareness ('let's move on', 'think about this more carefully'). "
        "Only provide feedback at the end of the session (debrief mode). "
        "Assess interview performance, not learning."
    ),
    "improvement": (
        "a focused remediation tutor. The candidate has a specific gap to close. "
        "Zero in on the weak concept with worked examples and guided practice. "
        "Be supportive but stay on topic — don't drift to other concepts."
    ),
}

# ── Teaching techniques ──────────────────────────────────────────────────────

_TECHNIQUES = {
    "socratic_questioning": (
        "Ask probing questions that guide the candidate to the answer themselves. "
        "Do not explain — ask questions instead."
    ),
    "worked_example": (
        "Walk through a concrete worked example step-by-step. "
        "Show the process, then ask the candidate to apply it."
    ),
    "analogical_reasoning": (
        "Use a relatable analogy from everyday life or a simpler domain to explain the concept. "
        "Then connect it back to the technical context."
    ),
    "elaborative_interrogation": (
        "Ask 'why does this work?' and 'what would happen if...?' questions. "
        "Push the candidate to articulate their reasoning explicitly."
    ),
    "error_analysis": (
        "Present a common mistake or misconception about this concept. "
        "Ask the candidate to identify the error and explain why it is wrong."
    ),
    "think_aloud": (
        "Ask the candidate to think aloud as they work through the problem. "
        "Listen for reasoning gaps and address them with targeted questions."
    ),
    "concept_mapping": (
        "Ask the candidate to connect this concept to related concepts they already know. "
        "How does it fit into the bigger picture?"
    ),
    "spaced_retrieval": (
        "Ask the candidate to recall and explain a concept they covered earlier in the session, "
        "then connect it to the current topic."
    ),
}


def _select_technique(channel: str, last_quality: str | None) -> tuple[str, str]:
    mapping = {
        ("foundation", None):      "worked_example",
        ("foundation", "wrong"):   "analogical_reasoning",
        ("foundation", "partial"): "elaborative_interrogation",
        ("foundation", "correct"): "concept_mapping",
        ("deepdive", None):        "socratic_questioning",
        ("deepdive", "wrong"):     "error_analysis",
        ("deepdive", "partial"):   "socratic_questioning",
        ("deepdive", "correct"):   "think_aloud",
        ("simulation", None):      "think_aloud",
        ("simulation", "wrong"):   "think_aloud",
        ("simulation", "partial"): "think_aloud",
        ("simulation", "correct"): "think_aloud",
        ("improvement", None):     "worked_example",
        ("improvement", "wrong"):  "worked_example",
        ("improvement", "partial"):"elaborative_interrogation",
        ("improvement", "correct"):"concept_mapping",
    }
    name = mapping.get((channel, last_quality), "socratic_questioning")
    return name, _TECHNIQUES[name]


def _build_system_prompt(
    channel: str,
    candidate_level: str,
    current_concept_tag: str,
    covered_concepts: list[str],
    required_concepts: list[str],
    gaps: list[str],
    strengths: list[str],
    section_name: str,
    section_description: str,
    current_question_text: str | None,
    technique_name: str,
    technique_instruction: str,
) -> str:
    persona = _PERSONAS.get(channel, _PERSONAS["foundation"])
    uncovered = [c for c in required_concepts if c not in covered_concepts]

    question_ctx = (
        f"The question you are currently exploring with them:\n  \"{current_question_text}\""
        if current_question_text
        else f"Explore the concept {current_concept_tag} conversationally — no set question."
    )

    return f"""You are {persona}

Context:
  Candidate level: {candidate_level} | Channel: {channel}
  Section: {section_name} — {section_description}
  Current concept: {current_concept_tag}
  Concepts still to cover: {uncovered}
  {question_ctx}
  Candidate gaps: {gaps or 'none yet'} | Strengths: {strengths or 'none yet'}

Teaching technique: {technique_name} — {technique_instruction}

CONVERSATION RULES (follow these strictly):
1. RESPOND FIRST to exactly what the candidate just said.
   - If they answered something: acknowledge it specifically (what was right, what was missing).
   - If they asked a doubt or said they're confused: address that doubt directly before anything else.
   - If they went off-topic: gently redirect back to {current_concept_tag}.
   - Never ignore what they said and jump straight into explaining.

2. KEEP IT SHORT. 2–3 sentences of response, then ONE question. No long lectures.
   - If they need more explanation, give one example, then ask if that clarifies it.
   - If they understood, move the conversation forward with a harder follow-up.

3. ALWAYS end your response with EXACTLY ONE question. Never end without asking something.
   - Use the question to either check understanding, push deeper, or invite doubts.
   - Good endings: "Does that make sense?", "What do you think happens when...?", "Can you give me an example of...?", "What's unclear so far?"

4. Do NOT write bullet-point notes or lecture-style paragraphs. This is a conversation, not a lesson.

5. After your response, append this hidden signal on its own line (never mention it to the candidate):
<signal>{{"concept_tag":"{current_concept_tag}","quality":"QUALITY"}}</signal>
Replace QUALITY with: wrong (misunderstood or no attempt), partial (on the right track but incomplete), correct (clear understanding shown)."""


def extract_signal(text: str) -> dict | None:
    """Extract and parse the hidden signal tag from the mentor's response."""
    match = re.search(r"<signal>(.*?)</signal>", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def strip_signal(text: str) -> str:
    """Remove the signal tag from the text before sending to the client."""
    return re.sub(r"\s*<signal>.*?</signal>\s*$", "", text, flags=re.DOTALL).strip()


def get_opening_message(
    channel: str,
    candidate_level: str,
    section_name: str,
    first_concept_tag: str,
    first_question_text: str | None,
    gaps: list[str],
) -> str:
    """
    Generate the mentor's first message when a session starts.
    Gives the candidate context and asks the opening question naturally.
    Called once by create_session so the candidate doesn't have to speak first.
    """
    persona = _PERSONAS.get(channel, _PERSONAS["foundation"])
    concept_display = first_concept_tag.replace("_", " ")
    question_line = (
        f'Start by asking them this question naturally (don\'t quote it verbatim — rephrase it conversationally):\n  "{first_question_text}"'
        if first_question_text
        else f"Open with a question that probes their current knowledge of {concept_display}."
    )
    gap_note = (
        f"Note: they have known gaps in {', '.join(gaps)} — be especially patient on those."
        if gaps else ""
    )

    system = (
        f"You are {persona}\n\n"
        f"You are starting a new mentoring session for a {candidate_level}-level candidate.\n"
        f"Section: {section_name}\n"
        f"First concept to explore: {concept_display}\n"
        f"{gap_note}\n\n"
        f"Write a SHORT opening message (2–3 sentences max) that:\n"
        f"1. Greets the candidate warmly and states what concept you'll start with.\n"
        f"2. {question_line}\n"
        f"3. Makes it clear they can ask doubts at any point.\n\n"
        f"Do NOT use the signal tag here. This is just the opening greeting."
    )

    response = _client.chat.completions.create(
        model=_MODEL,
        max_tokens=256,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": "Start the session."},
        ],
    )
    return response.choices[0].message.content.strip()


def stream_mentor_response(
    channel: str,
    candidate_level: str,
    current_concept_tag: str,
    covered_concepts: list[str],
    required_concepts: list[str],
    gaps: list[str],
    strengths: list[str],
    section_name: str,
    section_description: str,
    current_question_text: str | None,
    last_quality: str | None,
    chat_history: list[dict],
    user_message: str,
) -> tuple[str, dict | None]:
    """
    Call the Mentor Agent and return (clean_response, signal_dict).

    Streams from Grok internally to collect the full response, then strips
    the signal before returning to the router.
    """
    technique_name, technique_instruction = _select_technique(channel, last_quality)

    system_prompt = _build_system_prompt(
        channel=channel,
        candidate_level=candidate_level,
        current_concept_tag=current_concept_tag,
        covered_concepts=covered_concepts,
        required_concepts=required_concepts,
        gaps=gaps,
        strengths=strengths,
        section_name=section_name,
        section_description=section_description,
        current_question_text=current_question_text,
        technique_name=technique_name,
        technique_instruction=technique_instruction,
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages += chat_history
    messages += [{"role": "user", "content": user_message}]

    full_text = ""
    stream = _client.chat.completions.create(
        model=_MODEL,
        max_tokens=1024,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            full_text += delta

    signal = extract_signal(full_text)
    clean = strip_signal(full_text)

    return clean, signal
