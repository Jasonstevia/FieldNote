# seo_common.py

import os
import json
import datetime
import typing as t, re
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
_genai_model = None
_genai_model_name = None
_genai_cooldown_until = 0.0

def gemini_model_candidates() -> list[str]:
    preferred_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    candidates = []
    for name in (
        preferred_model,
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ):
        if name not in candidates:
            candidates.append(name)
    return candidates

# --- Centralized AI Configuration ---

def genai_model():
    """
    A safe, centralized function to get the configured Generative AI model.
    It now assumes the environment variables are already loaded by the server.
    """
    global _genai_model, _genai_model_name
    preferred_model = gemini_model_candidates()[0]
    if _genai_model and _genai_model_name == preferred_model:
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
        last_error = None
        for model_name in gemini_model_candidates():
            try:
                candidate = genai.GenerativeModel(model_name)
                _genai_model = candidate
                _genai_model_name = model_name
                print(f"--- Gemini AI Model configured successfully: {model_name} ---")
                return _genai_model
            except Exception as e:
                last_error = e
                print(f"--- Warning: could not configure Gemini model {model_name}: {e} ---")

        print(f"--- FATAL ERROR configuring Google AI: {last_error} ---")
        return None
    except Exception as e:
        print(f"--- FATAL ERROR configuring Google AI: {e} ---")
        return None

def generate_with_fallback(prompt: str):
    """
    Generate content with automatic fallback across Gemini text models.
    This helps demos survive quota/model availability issues on a single model.
    """
    global _genai_cooldown_until
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    if time.time() < _genai_cooldown_until:
        return None

    genai.configure(api_key=api_key)
    timeout_seconds = float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "20"))
    last_error = None
    for model_name in gemini_model_candidates():
        try:
            model = genai.GenerativeModel(model_name)
            return model.generate_content(
                prompt,
                request_options={"timeout": timeout_seconds},
            )
        except Exception as e:
            last_error = e
            err_text = str(e).lower()
            if (
                "quota" in err_text
                or "429" in err_text
                or "rate limit" in err_text
                or "not found" in err_text
                or "deadline exceeded" in err_text
                or "timed out" in err_text
                or "timeout" in err_text
            ):
                retry_match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", err_text)
                if retry_match:
                    _genai_cooldown_until = max(_genai_cooldown_until, time.time() + float(retry_match.group(1)))
                elif "quota" in err_text or "429" in err_text:
                    _genai_cooldown_until = max(_genai_cooldown_until, time.time() + 30)
                print(f"--- Warning: generate_content failed on {model_name}, trying fallback: {e} ---")
                continue
            raise
    if last_error:
        raise last_error
    return None

# --- Utility Functions (No changes needed) ---
def today_iso():
    return datetime.datetime.utcnow().date().isoformat()

def safe_json(text: str) -> t.Optional[t.Union[dict, list]]:
    """
    DEFINITIVELY FIXED: More robustly finds and parses a JSON object OR ARRAY from a string,
    even if it's embedded in markdown.
    """
    try:
        # This regex now looks for either a '{' or a '[' to start the JSON.
        match = re.search(r'```json\s*([\[\{].*?[\]\}])\s*```', text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Fallback to find the first '{' or '[' and last '}' or ']'
            start = -1
            if text.find('{') != -1:
                start = text.find('{')
            elif text.find('[') != -1:
                start = text.find('[')

            end = -1
            if text.rfind('}') != -1:
                end = text.rfind('}')
            elif text.rfind(']') != -1:
                end = text.rfind(']')

            if start != -1 and end != -1:
                json_str = text[start:end+1]
            else:
                raise json.JSONDecodeError("No JSON object or array found", text, 0)

        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError) as e:
        print(f"Warning: Robust JSON decoding failed. Error: {e}. Raw text: {text[:200]}...")
        return None
