# api_server.py

import asyncio, uuid
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from context_store import load_context
from orchestrator import run_orchestrator_turn # Import the new function

# --- MODELS ---
class StartSessionResponse(BaseModel):
    session_id: str

class ChatBody(BaseModel):
    message: str

class ChatResponse(BaseModel):
    messages: List[Dict[str, Any]]

# --- APP SETUP ---
app = FastAPI(title="Vibe Orchestrator API", version="0.2.0") # Version bump!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- API ENDPOINTS ---
@app.get("/api/ping")
def ping():
    return {"ok": True}

@app.post("/api/session/start", response_model=StartSessionResponse)
async def start_session():
    """Starts a new session and returns a session_id."""
    session_id = str(uuid.uuid4())[:8]
    # No need for TASKS dictionary anymore, we will handle state in context
    return {"session_id": session_id}

@app.post("/api/session/{session_id}/chat", response_model=ChatResponse)
async def post_chat_message(session_id: str, body: ChatBody):
    """Handles the conversational turn with the orchestrator."""
    response_messages = await run_orchestrator_turn(session_id, body.message)
    return {"messages": response_messages}

@app.get("/api/session/{session_id}/context")
async def get_context(session_id: str):
    return load_context(session_id) or {"error": "No context found"}

from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="agent", html=True), name="static")