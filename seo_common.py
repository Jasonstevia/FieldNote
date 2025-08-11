# seo_common.py

import os
import json
import datetime
import typing as t, re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
_genai_model = None
# --- Centralized AI Configuration ---

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
        _genai_model = genai.GenerativeModel("gemini-2.5-pro")
        print("--- Gemini AI Model configured successfully. ---")
        return _genai_model
    except Exception as e:
        print(f"--- FATAL ERROR configuring Google AI: {e} ---")
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