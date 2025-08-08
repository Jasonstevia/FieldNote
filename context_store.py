"""context_store.py"""

import json, os, pathlib, typing as t

BASE = os.environ.get("VIBE_CONTEXT_DIR", ".vibe_context")
pathlib.Path(BASE).mkdir(parents=True, exist_ok=True)

def _path(session_id: str) -> str:
    safe = session_id.replace("/", "_")
    return str(pathlib.Path(BASE) / f"{safe}.json")

def save_context(session_id: str, ctx: t.Dict) -> None:
    p = _path(session_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)

def load_context(session_id: str) -> t.Optional[dict]:
    p = _path(session_id)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)