# context_store.py

import json, os, pathlib, typing as t

# Check if we are running in the Vercel environment
# If so, use the /tmp directory, which is the only writable location.
# Otherwise, use the local .vibe_context directory for local development.
IS_VERCEL = os.environ.get('VERCEL') == '1'
BASE_DIR = '/tmp/vibe_context' if IS_VERCEL else '.vibe_context'

# Ensure the base directory exists
pathlib.Path(BASE_DIR).mkdir(parents=True, exist_ok=True)

def _path(session_id: str) -> str:
    safe_id = session_id.replace("/", "_").replace("\\", "_")
    return str(pathlib.Path(BASE_DIR) / f"{safe_id}.json")

def save_context(session_id: str, ctx: t.Dict) -> None:
    p = _path(session_id)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ctx, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving context to {p}: {e}")

def load_context(session_id: str) -> t.Optional[dict]:
    p = _path(session_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading context from {p}: {e}")
        return None