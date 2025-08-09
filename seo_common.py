# seo_common.py

import os
import json
import datetime
import typing as t
import google.generativeai as genai
# We no longer need dotenv here, the server will handle it.

# --- Centralized AI Configuration ---

_genai_model = None

def genai_model():
    """
    A safe, centralized function to get the configured Generative AI model.
    It now assumes the environment variables are already loaded by the server.
    """
    global _genai_model
    if _genai_model:
        return _genai_model

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("---")
        print("WARNING: GEMINI_API_KEY not found in environment.")
        print("Ensure you are running uvicorn with the --env-file .env flag.")
        print("---")
        return None

    try:
        genai.configure(api_key=api_key)
        _genai_model = genai.GenerativeModel("gemini-1.5-flash")
        print("--- Gemini AI Model configured successfully. ---")
        return _genai_model
    except Exception as e:
        print(f"--- FATAL ERROR configuring Google AI: {e} ---")
        return None

# --- Utility Functions (No changes needed) ---
def today_iso():
    return datetime.datetime.utcnow().date().isoformat()

def safe_json(text: str) -> t.Optional[dict]:
    try:
        clean_text = text.strip().lstrip("```json").rstrip("```")
        return json.loads(clean_text)
    except json.JSONDecodeError:
        print(f"Warning: Failed to decode JSON from AI response: {text[:200]}...")
        return None