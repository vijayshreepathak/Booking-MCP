"""
FastAPI app + MCP server registration.
MCP interface: custom registry (no fastapi_mcp package).
"""
import os
import uuid
from typing import Any, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db, init_db, SessionLocal
from app.models import Session as DBSession, PromptHistory
from app.tools import check_availability, create_appointment, query_stats, send_notification
from app.mcp_registry import get_tools_metadata

# LLM orchestration (demo or real)
from app.llm_orchestrator import get_llm_response, build_messages_from_history

app = FastAPI(
    title="Agentic Appointment MCP",
    description="MCP-powered doctor appointment and reporting assistant",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request/Response models ---
class MCPToolCallRequest(BaseModel):
    doctor_name: Optional[str] = None
    date_str: Optional[str] = None
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None
    slot_id: Optional[int] = None
    start_time_str: Optional[str] = None
    symptom: Optional[str] = "general"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    symptom_filter: Optional[str] = None
    recipient: Optional[str] = None
    message: Optional[str] = None
    channel: Optional[str] = "slack"


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    tool_calls: Optional[list[dict]] = None


class DoctorSummaryRequest(BaseModel):
    doctor_name: str
    prompt: Optional[str] = None


# --- Startup: init DB ---
@app.on_event("startup")
def startup():
    init_db()


# --- Session creation (for frontend) ---
@app.post("/api/sessions")
def create_session():
    """Create a new session. Returns session_id for frontend persistence."""
    session_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        s = DBSession(session_id=session_id, role="patient")
        db.add(s)
        db.commit()
        return {"session_id": session_id}
    finally:
        db.close()


# --- MCP endpoints ---
@app.get("/mcp/tools")
def list_mcp_tools():
    """Return MCP tool metadata for LLM agent discovery."""
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return get_tools_metadata(base_url)


TOOL_HANDLERS = {
    "check_availability": lambda db, d: check_availability(
        db, d.get("doctor_name", ""), d.get("date_str", "")
    ),
    "create_appointment": lambda db, d: create_appointment(
        db,
        d.get("doctor_name", ""),
        d.get("patient_name", ""),
        d.get("patient_email", ""),
        slot_id=d.get("slot_id"),
        date_str=d.get("date_str"),
        start_time_str=d.get("start_time_str"),
        symptom=d.get("symptom", "general"),
    ),
    "query_stats": lambda db, d: query_stats(
        db,
        doctor_name=d.get("doctor_name"),
        start_date=d.get("start_date"),
        end_date=d.get("end_date"),
        symptom_filter=d.get("symptom_filter"),
    ),
    "send_notification": lambda db, d: send_notification(
        db,
        d.get("recipient", ""),
        d.get("message", ""),
        d.get("channel", "slack"),
    ),
}


@app.post("/mcp/tools/{tool_name}/call")
def call_mcp_tool(tool_name: str, body: MCPToolCallRequest, db: Session = Depends(get_db)):
    """Invoke an MCP tool by name."""
    if tool_name not in TOOL_HANDLERS:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    data = body.model_dump(exclude_none=True)
    result = TOOL_HANDLERS[tool_name](db, data)
    return result


# --- Session creation ---
@app.post("/api/sessions")
def create_session():
    """Create a new session. Returns session_id for frontend persistence."""
    return {"session_id": str(uuid.uuid4())}


# --- Session creation (for frontend) ---
@app.post("/api/sessions")
def create_session():
    """Create a new session. Returns session_id for multi-turn chat."""
    import uuid
    return {"session_id": str(uuid.uuid4())}


# --- Sessions (for frontend) ---
@app.post("/api/sessions")
def create_session():
    """Create a new chat session. Returns session_id for persistence."""
    import uuid
    return {"session_id": str(uuid.uuid4())}


# --- Session creation (for frontend) ---
@app.post("/api/sessions")
def create_session():
    """Create a new chat session. Returns session_id for multi-turn conversation."""
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}


# --- Chat API (multi-turn with LLM) ---
@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Multi-turn chat. Creates/loads session, persists history, calls LLM with tool support.
    Returns final assistant text.
    """
    session = db.query(DBSession).filter(DBSession.session_id == req.session_id).first()
    if not session:
        session = DBSession(session_id=req.session_id, role="patient")
        db.add(session)
        db.commit()
        db.refresh(session)

    # Save user message
    user_entry = PromptHistory(session_id=session.id, role="user", content=req.message)
    db.add(user_entry)
    db.commit()

    # Build messages from history (last N) and call LLM
    messages = build_messages_from_history(db, session.id)
    messages.append({"role": "user", "content": req.message})

    response_text, tool_calls_used = get_llm_response(messages, db)

    # Save assistant response
    import json
    asst_entry = PromptHistory(
        session_id=session.id,
        role="assistant",
        content=response_text,
        tool_calls=json.dumps(tool_calls_used) if tool_calls_used else None,
    )
    db.add(asst_entry)
    db.commit()

    return ChatResponse(
        session_id=req.session_id,
        response=response_text,
        tool_calls=tool_calls_used,
    )


# --- Doctor summary API ---
@app.post("/api/doctor/summary")
def api_doctor_summary(req: DoctorSummaryRequest, db: Session = Depends(get_db)):
    """
    Doctor summary report. Uses query_stats and optional send_notification.
    Returns human-readable report.
    """
    from datetime import datetime, timedelta
    from app.llm_orchestrator import get_llm_response

    # Build stats via query_stats
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    stats_today = query_stats(db, doctor_name=req.doctor_name, start_date=str(today), end_date=str(today))
    stats_yesterday = query_stats(db, doctor_name=req.doctor_name, start_date=str(yesterday), end_date=str(yesterday))
    stats_tomorrow = query_stats(db, doctor_name=req.doctor_name, start_date=str(tomorrow), end_date=str(tomorrow))

    prompt = req.prompt or "Summarize my schedule"
    system = """You are a medical assistant. Summarize the following doctor appointment statistics into a brief, human-readable report.
Format: bullet points. Mention today, yesterday, tomorrow counts.
Do not make up numbers; only use what is provided."""

    stats_text = f"""Today: {stats_today['total_appointments']} appointments.
Yesterday: {stats_yesterday['total_appointments']} appointments.
Tomorrow: {stats_tomorrow['total_appointments']} appointments.
By date breakdown - Today: {stats_today.get('by_date', {})}, Yesterday: {stats_yesterday.get('by_date', {})}, Tomorrow: {stats_tomorrow.get('by_date', {})}."""

    if os.getenv("LLM_PROVIDER", "demo") == "demo":
        report = f"""**Schedule Summary for {req.doctor_name}**
• Today: {stats_today['total_appointments']} appointments
• Yesterday: {stats_yesterday['total_appointments']} appointments
• Tomorrow: {stats_tomorrow['total_appointments']} appointments
{stats_text}"""
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Prompt: {prompt}\n\nData:\n{stats_text}"},
        ]
        report, _ = get_llm_response(messages, db)

    return {
        "doctor_name": req.doctor_name,
        "report": report,
        "stats": {
            "today": stats_today["total_appointments"],
            "yesterday": stats_yesterday["total_appointments"],
            "tomorrow": stats_tomorrow["total_appointments"],
        },
    }


# --- Health ---
@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
