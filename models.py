from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # executive | feeder | candidate
    hashed_pw = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LearningPath(Base):
    __tablename__ = "learning_paths"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    seniority = Column(String, default="mid")  # junior | mid | senior
    language = Column(String, default="")
    # JSON list of sample question strings, used as style hints by question_gen
    sample_questions = Column(Text, default="[]")
    status = Column(String, default="draft")  # draft | published


class EvalPattern(Base):
    __tablename__ = "eval_patterns"
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    # JSON list of sample question strings for this pattern (e.g. code snippets, DSA problems)
    sample_patterns = Column(Text, default="[]")
    order_index = Column(Integer, default=0)


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True, index=True)
    learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    order_index = Column(Integer, default=0)
    # JSON list of concept tag strings e.g. '["python_types","python_functions"]'
    concepts = Column(Text, default="[]")
    # Free text rubric used by the evaluator agent
    rubric = Column(Text, default="")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    concept_tag = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    difficulty_band = Column(String, nullable=False)  # foundational | deepdive | interview_ready
    seniority = Column(String, default="mid")
    pattern_type = Column(String, default="conceptual")  # conceptual | scenario | problem_solving
    is_preliminary = Column(Boolean, default=False)


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    learning_path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=True)
    # Channel the candidate is currently in
    channel = Column(String, default="")  # foundation | deepdive | simulation | improvement
    level = Column(String, default="")    # junior | mid | senior
    # JSON lists stored as text
    gaps = Column(Text, default="[]")
    strengths = Column(Text, default="[]")
    # Saved before entering improvement channel so we can return
    pre_improvement_channel = Column(String, nullable=True)
    interview_ready = Column(Boolean, default=False)
    # 0–100 composite readiness score updated after each advancement assessment
    readiness_score = Column(Float, nullable=True)
    plan_id = Column(Integer, ForeignKey("candidate_plans.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CandidatePlan(Base):
    __tablename__ = "candidate_plans"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    # JSON: list of section ids in order
    section_order = Column(Text, default="[]")
    # JSON: {concept_tag: float weight}
    concept_weights = Column(Text, default="{}")
    # JSON: {pattern_type: float weight}
    pattern_weights = Column(Text, default="{}")
    # JSON: {concept_tag: "foundational"|"deepdive"|"interview_ready"}
    difficulty_start = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    channel = Column(String, nullable=False)  # channel at session creation time
    current_concept_tag = Column(String, nullable=True)
    # JSON lists
    covered_concepts = Column(Text, default="[]")
    required_concepts = Column(Text, default="[]")
    answer_count = Column(Integer, default=0)
    status = Column(String, default="active")  # active | ended
    created_at = Column(DateTime, default=datetime.utcnow)


class SessionAnswer(Base):
    __tablename__ = "session_answers"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    candidate_answer = Column(Text)
    concept_tag = Column(String)
    quality = Column(String)  # wrong | partial | correct
    created_at = Column(DateTime, default=datetime.utcnow)


class Assessment(Base):
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    assessment_type = Column(String, nullable=False)  # preliminary_test | topic_gate | mock_interview
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=True)
    status = Column(String, default="pending")  # pending | submitted | evaluated
    # JSON list of question ids for this assessment
    question_ids = Column(Text, default="[]")
    # JSON result dict stored after evaluation
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"
    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    candidate_answer = Column(Text)


class CandidateQuestionHistory(Base):
    __tablename__ = "candidate_question_history"
    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    last_quality = Column(String)   # wrong | partial | correct
    times_seen = Column(Integer, default=1)
