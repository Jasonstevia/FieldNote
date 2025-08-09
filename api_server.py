# api_server.py

import os, uuid
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse # Import the RedirectResponse class
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from context_store import load_context
from orchestrator import run_orchestrator_turn, execute_with_keys

# --- MODELS ---
class StartSessionResponse(BaseModel): session_id: str
class ChatBody(BaseModel): message: str; api_keys: Optional[dict] = None
class ExecuteBody(BaseModel): creds: dict
class ChatResponse(BaseModel): messages: List[Dict[str, Any]]

# --- APP SETUP ---
app = FastAPI(title="FieldNote API", version="1.0.0") # Let's call it 1.0!

allow_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=allow_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- API ENDPOINTS ---

# THIS IS THE NEW, PERMANENT FIX
@app.get("/")
async def root_redirect():
    """Redirects the root URL ('/') to the main homepage."""
    return RedirectResponse(url="/index.html")

@app.post("/api/session/start", response_model=StartSessionResponse)
async def start_session(): return {"session_id": str(uuid.uuid4())[:8]}

@app.post("/api/session/{session_id}/chat", response_model=ChatResponse)
async def post_chat_message(session_id: str, body: ChatBody):
    response_messages = await run_orchestrator_turn(session_id, body.message, api_keys=body.api_keys)
    return {"messages": response_messages}

@app.post("/api/session/{session_id}/execute", response_model=ChatResponse)
async def execute_changes(session_id: str, body: ExecuteBody):
    logs = await execute_with_keys(session_id, body.creds)
    return {"messages": logs}

@app.get("/api/session/{session_id}/review")
async def get_review_data(session_id: str):
    ctx = load_context(session_id)
    if not ctx: return {"error": "No context."}
    return {
        "onpage_seo": ctx.get("agents", {}).get("onpage_seo", {}).get("proposals", []),
        "meta_optimization": ctx.get("agents", {}).get("meta_optimization", {}).get("proposals", []),
        "blog_automation": ctx.get("agents", {}).get("blog_automation", {}).get("schedule", []),
    }

# This must come AFTER all other routes
from fastapi.staticfiles import StaticFiles
if os.path.isdir("agent"):
    app.mount("/", StaticFiles(directory="agent", html=True), name="static")