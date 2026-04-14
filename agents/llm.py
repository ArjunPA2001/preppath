"""
Shared LLM client for all agents.
All three agents import their client and model constants from here.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

# Model used by Mentor and Plan Gen (higher quality, used for generation)
FAST_MODEL = "llama-3.1-8b-instant"

# Model used by Evaluator (fast and cheap, used for structured JSON eval)
SMART_MODEL = "openai/gpt-oss-120b"
