"""seo_common.py"""

import os, json, datetime, typing as t
try:
    import google.generativeai as genai
except Exception:
    genai = None

from context_store import load_context, save_context

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro-latest")

def llm_enabled() -> bool:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return bool(key and genai)

def genai_model():
    if not llm_enabled():
        return None
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    genai.configure(api_key=key)
    return genai.GenerativeModel(DEFAULT_MODEL)

def today_iso():
    return datetime.datetime.utcnow().date().isoformat()

def safe_json(text: str) -> t.Optional[dict]:
    try:
        return json.loads(text)
    except Exception:
        return None