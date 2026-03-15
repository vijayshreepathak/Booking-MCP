"""FastAPI app, MCP registry, and product APIs."""
from contextlib import asynccontextmanager
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db, init_db
from app.llm_orchestrator import build_messages_from_history, get_llm_response
from app.mcp_registry import get_tools_metadata
from app.models import PromptHistory, Session as DBSession
from app.tools import (
    cancel_appointment,
    check_availability,
    create_appointment,
    list_doctors,
    list_patient_appointments,
    query_stats,
    reschedule_appointment,
    send_notification,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Agentic Appointment MCP",
    description="MCP-powered doctor appointment and reporting assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MCPToolCallRequest(BaseModel):
    doctor_name: Optional[str] = None
    date_str: Optional[str] = None
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None
    appointment_id: Optional[int] = None
    slot_id: Optional[int] = None
    new_slot_id: Optional[int] = None
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
    patient_name: Optional[str] = None
    patient_email: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    session_label: str
    response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    available_slots: list[dict[str, Any]] = Field(default_factory=list)
    alternative_slots: list[dict[str, Any]] = Field(default_factory=list)
    appointment: Optional[dict[str, Any]] = None


class DoctorSummaryRequest(BaseModel):
    doctor_name: str
    prompt: Optional[str] = None


class LoginRequest(BaseModel):
    role: str
    email: str
    password: str
    name: Optional[str] = None


class LoginResponse(BaseModel):
    session_id: str
    role: str
    name: str
    email: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    session_label: str
    messages: list[dict[str, Any]] = Field(default_factory=list)


class PatientAppointmentActionRequest(BaseModel):
    patient_email: str
    doctor_name: Optional[str] = None
    new_slot_id: Optional[int] = None
    date_str: Optional[str] = None
    start_time_str: Optional[str] = None


def _get_or_create_session(db: Session, session_id: str) -> DBSession:
    session = db.query(DBSession).filter(DBSession.session_id == session_id).first()
    if session:
        return session

    session = DBSession(session_id=session_id, role="patient")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _session_label(session_id: str) -> str:
    return f"Session {session_id.split('-')[0]}"


def _extract_chat_payload(
    tool_calls: Optional[list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]], list[dict[str, Any]]]:
    available_slots: list[dict[str, Any]] = []
    appointment: Optional[dict[str, Any]] = None
    alternative_slots: list[dict[str, Any]] = []

    for tool_call in tool_calls or []:
        result = tool_call.get("result", {})
        if tool_call.get("tool") == "check_availability":
            available_slots = result.get("available_slots", [])
        if tool_call.get("tool") == "create_appointment":
            alternative_slots = result.get("alternative_slots", [])
        if tool_call.get("tool") == "create_appointment" and result.get("success"):
            appointment = result
        if tool_call.get("tool") == "reschedule_appointment":
            alternative_slots = result.get("alternative_slots", [])
            if result.get("success"):
                appointment = result.get("appointment")
        if tool_call.get("tool") == "cancel_appointment" and result.get("success"):
            appointment = result.get("appointment")

    return available_slots, appointment, alternative_slots


def _history_payload(db: Session, session: DBSession) -> list[dict[str, Any]]:
    history = (
        db.query(PromptHistory)
        .filter(PromptHistory.session_id == session.id)
        .order_by(PromptHistory.created_at.asc())
        .all()
    )
    messages: list[dict[str, Any]] = []
    for item in history:
        tool_calls = json.loads(item.tool_calls) if item.tool_calls else []
        available_slots, appointment, alternative_slots = _extract_chat_payload(tool_calls)
        messages.append(
            {
                "role": item.role,
                "content": item.content,
                "toolCalls": tool_calls,
                "availableSlots": available_slots,
                "appointment": appointment,
                "alternativeSlots": alternative_slots,
            }
        )
    return messages


def _parse_summary_preferences(prompt: str) -> dict[str, Any]:
    lowered = (prompt or "").lower()
    include_days = {
        "yesterday": "yesterday" in lowered or not lowered,
        "today": "today" in lowered or not lowered,
        "tomorrow": "tomorrow" in lowered or not lowered,
    }
    symptom_filter = None
    common_symptoms = ["fever", "cough", "cold", "headache", "pain"]
    for symptom in common_symptoms:
        if symptom in lowered:
            symptom_filter = symptom
            break
    return {"include_days": include_days, "symptom_filter": symptom_filter}


def _demo_credentials() -> dict[str, dict[str, str]]:
    return {
        "patient": {
            "email": os.getenv("DEMO_PATIENT_EMAIL", "patient@demo.local"),
            "password": os.getenv("DEMO_PATIENT_PASSWORD", "patient123"),
            "name": os.getenv("DEMO_PATIENT_NAME", "Demo Patient"),
        },
        "doctor": {
            "email": os.getenv("DEMO_DOCTOR_EMAIL", "doctor@demo.local"),
            "password": os.getenv("DEMO_DOCTOR_PASSWORD", "doctor123"),
            "name": os.getenv("DEMO_DOCTOR_NAME", "Dr. Ahuja"),
        },
    }


TOOL_HANDLERS = {
    "list_doctors": lambda db, data: list_doctors(db),
    "check_availability": lambda db, data: check_availability(
        db, data.get("doctor_name", ""), data.get("date_str", "")
    ),
    "create_appointment": lambda db, data: create_appointment(
        db,
        data.get("doctor_name", ""),
        data.get("patient_name", ""),
        data.get("patient_email", ""),
        slot_id=data.get("slot_id"),
        date_str=data.get("date_str"),
        start_time_str=data.get("start_time_str"),
        symptom=data.get("symptom", "general"),
    ),
    "query_stats": lambda db, data: query_stats(
        db,
        doctor_name=data.get("doctor_name"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        symptom_filter=data.get("symptom_filter"),
    ),
    "send_notification": lambda db, data: send_notification(
        db,
        data.get("recipient", ""),
        data.get("message", ""),
        data.get("channel", "slack"),
    ),
    "list_patient_appointments": lambda db, data: list_patient_appointments(
        db,
        data.get("patient_email", ""),
    ),
    "cancel_appointment": lambda db, data: cancel_appointment(
        db,
        data.get("appointment_id"),
        data.get("patient_email", ""),
    ),
    "reschedule_appointment": lambda db, data: reschedule_appointment(
        db,
        data.get("appointment_id"),
        data.get("patient_email", ""),
        new_slot_id=data.get("new_slot_id") or data.get("slot_id"),
        doctor_name=data.get("doctor_name"),
        date_str=data.get("date_str"),
        start_time_str=data.get("start_time_str"),
    ),
}


@app.post("/api/sessions")
def create_session() -> dict[str, str]:
    session_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(DBSession(session_id=session_id, role="patient"))
        db.commit()
        return {"session_id": session_id}
    finally:
        db.close()


@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    credentials = _demo_credentials().get(req.role.lower())
    if not credentials:
        raise HTTPException(status_code=400, detail="Role must be either patient or doctor.")
    if req.email != credentials["email"] or req.password != credentials["password"]:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    session_id = str(uuid.uuid4())
    session = DBSession(session_id=session_id, role=req.role.lower())
    db.add(session)
    db.commit()
    return LoginResponse(
        session_id=session_id,
        role=req.role.lower(),
        name=req.name or credentials["name"],
        email=req.email,
    )


@app.get("/api/sessions/{session_id}/history", response_model=SessionHistoryResponse)
def get_session_history(session_id: str, db: Session = Depends(get_db)) -> SessionHistoryResponse:
    session = _get_or_create_session(db, session_id)
    return SessionHistoryResponse(
        session_id=session.session_id,
        session_label=_session_label(session.session_id),
        messages=_history_payload(db, session),
    )


@app.get("/api/doctors")
def get_doctors(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_doctors(db)


@app.get("/api/patient/appointments")
def get_patient_appointments(patient_email: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_patient_appointments(db, patient_email)


@app.delete("/api/patient/appointments/{appointment_id}")
def delete_patient_appointment(
    appointment_id: int,
    patient_email: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return cancel_appointment(db, appointment_id, patient_email)


@app.post("/api/patient/appointments/{appointment_id}/reschedule")
def change_patient_appointment(
    appointment_id: int,
    req: PatientAppointmentActionRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return reschedule_appointment(
        db,
        appointment_id,
        req.patient_email,
        new_slot_id=req.new_slot_id,
        doctor_name=req.doctor_name,
        date_str=req.date_str,
        start_time_str=req.start_time_str,
    )


@app.get("/mcp/tools")
def list_mcp_tools() -> list[dict[str, Any]]:
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    return get_tools_metadata(base_url)


@app.post("/mcp/tools/{tool_name}/call")
def call_mcp_tool(tool_name: str, body: MCPToolCallRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if tool_name not in TOOL_HANDLERS:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return TOOL_HANDLERS[tool_name](db, body.model_dump(exclude_none=True))


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    session = _get_or_create_session(db, req.session_id)

    db.add(PromptHistory(session_id=session.id, role="user", content=req.message))
    db.commit()

    messages = build_messages_from_history(db, session.id)
    messages.append({"role": "user", "content": req.message})

    response_text, tool_calls_used = get_llm_response(
        messages,
        db,
        patient_context={
            "patient_name": req.patient_name,
            "patient_email": req.patient_email,
        },
    )

    db.add(
        PromptHistory(
            session_id=session.id,
            role="assistant",
            content=response_text,
            tool_calls=json.dumps(tool_calls_used) if tool_calls_used else None,
        )
    )
    db.commit()

    available_slots, appointment, alternative_slots = _extract_chat_payload(tool_calls_used)
    return ChatResponse(
        session_id=req.session_id,
        session_label=_session_label(req.session_id),
        response=response_text,
        tool_calls=tool_calls_used or [],
        available_slots=available_slots,
        alternative_slots=alternative_slots,
        appointment=appointment,
    )


@app.post("/api/doctor/summary")
def api_doctor_summary(req: DoctorSummaryRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    preferences = _parse_summary_preferences(req.prompt or "")
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    stats_today = query_stats(
        db,
        doctor_name=req.doctor_name,
        start_date=str(today),
        end_date=str(today),
        symptom_filter=preferences["symptom_filter"],
    )
    stats_yesterday = query_stats(
        db,
        doctor_name=req.doctor_name,
        start_date=str(yesterday),
        end_date=str(yesterday),
        symptom_filter=preferences["symptom_filter"],
    )
    stats_tomorrow = query_stats(
        db,
        doctor_name=req.doctor_name,
        start_date=str(tomorrow),
        end_date=str(tomorrow),
        symptom_filter=preferences["symptom_filter"],
    )

    report_lines = [f"Schedule summary for {req.doctor_name}"]
    if preferences["symptom_filter"]:
        report_lines.append(f"Filtered by symptom: {preferences['symptom_filter']}")
    if preferences["include_days"]["yesterday"]:
        report_lines.append(f"Yesterday: {stats_yesterday['total_appointments']} appointments")
    if preferences["include_days"]["today"]:
        report_lines.append(f"Today: {stats_today['total_appointments']} appointments")
        if stats_today.get("symptoms"):
            symptom_summary = ", ".join(
                f"{symptom}: {count}" for symptom, count in stats_today["symptoms"].items()
            )
            report_lines.append(f"Today's symptom mix: {symptom_summary}")
    if preferences["include_days"]["tomorrow"]:
        report_lines.append(f"Tomorrow: {stats_tomorrow['total_appointments']} appointments")

    report = "\n".join(report_lines)
    notification = send_notification(
        db,
        recipient=req.doctor_name,
        message=report,
        channel="slack",
    )

    return {
        "doctor_name": req.doctor_name,
        "report": report,
        "stats": {
            "today": stats_today["total_appointments"],
            "yesterday": stats_yesterday["total_appointments"],
            "tomorrow": stats_tomorrow["total_appointments"],
            "symptom_filter": preferences["symptom_filter"],
            "daily_breakdown": {
                "today": stats_today.get("by_date", {}),
                "yesterday": stats_yesterday.get("by_date", {}),
                "tomorrow": stats_tomorrow.get("by_date", {}),
            },
        },
        "notification": notification,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
