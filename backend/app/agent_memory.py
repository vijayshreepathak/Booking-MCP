"""Structured session memory for multi-turn agent workflows."""
import json
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AgentMemory


def _default_memory() -> dict[str, Any]:
    return {
        "patient_name": None,
        "patient_email": None,
        "selected_doctor": None,
        "requested_date": None,
        "requested_time": None,
        "time_preference": None,
        "last_available_slots": [],
        "last_appointment_id": None,
        "last_appointment": None,
        "active_appointments": [],
        "last_intent": None,
    }


def get_or_create_memory(db: Session, session_primary_id: int) -> AgentMemory:
    memory = db.query(AgentMemory).filter(AgentMemory.session_id == session_primary_id).first()
    if memory:
        return memory

    memory = AgentMemory(session_id=session_primary_id, summary="", memory_json=json.dumps(_default_memory()))
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def load_memory(db: Session, session_primary_id: int) -> dict[str, Any]:
    memory = get_or_create_memory(db, session_primary_id)
    try:
        payload = json.loads(memory.memory_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {**_default_memory(), **payload}


def _summarize(memory: dict[str, Any]) -> str:
    parts = []
    if memory.get("patient_name") or memory.get("patient_email"):
        parts.append(
            "Patient: "
            f"{memory.get('patient_name') or 'unknown'}"
            f" ({memory.get('patient_email') or 'no email'})"
        )
    if memory.get("selected_doctor"):
        parts.append(f"Preferred doctor: {memory['selected_doctor']}")
    if memory.get("requested_date"):
        when = memory["requested_date"]
        if memory.get("requested_time"):
            when += f" at {memory['requested_time']}"
        elif memory.get("time_preference"):
            when += f" ({memory['time_preference']})"
        parts.append(f"Requested date/time: {when}")
    if memory.get("last_available_slots"):
        slot_preview = ", ".join(
            f"{slot.get('slot_id')}:{slot.get('date')} {slot.get('start_time')}"
            for slot in memory["last_available_slots"][:3]
        )
        parts.append(f"Last offered slots: {slot_preview}")
    if memory.get("last_appointment"):
        appt = memory["last_appointment"]
        parts.append(
            f"Last appointment #{appt.get('appointment_id')} with {appt.get('doctor')} "
            f"on {appt.get('date')} at {appt.get('start_time')} ({appt.get('status')})"
        )
    if memory.get("active_appointments"):
        ids = ", ".join(str(appt.get("appointment_id")) for appt in memory["active_appointments"][:5])
        parts.append(f"Active appointments: {ids}")
    if memory.get("last_intent"):
        parts.append(f"Last intent: {memory['last_intent']}")
    return " | ".join(parts)


def persist_memory(db: Session, session_primary_id: int, memory_payload: dict[str, Any]) -> dict[str, Any]:
    memory = get_or_create_memory(db, session_primary_id)
    memory.summary = _summarize(memory_payload)
    memory.memory_json = json.dumps(memory_payload)
    db.commit()
    return memory_payload


def _extract_time_preference(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    for word in ["morning", "afternoon", "evening"]:
        if word in lowered:
            return word
    return None


def update_memory_from_user_message(
    db: Session,
    session_primary_id: int,
    message: str,
    patient_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    patient_context = patient_context or {}
    memory = load_memory(db, session_primary_id)
    lowered = (message or "").lower()

    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", message or "")
    if patient_context.get("patient_email"):
        memory["patient_email"] = patient_context["patient_email"]
    elif email_match:
        memory["patient_email"] = email_match.group(0)

    if patient_context.get("patient_name"):
        memory["patient_name"] = patient_context["patient_name"]

    if "dr. smith" in lowered or "smith" in lowered:
        memory["selected_doctor"] = "Dr. Smith"
    elif "dr. ahuja" in lowered or "ahuja" in lowered:
        memory["selected_doctor"] = "Dr. Ahuja"

    time_preference = _extract_time_preference(message)
    if time_preference:
        memory["time_preference"] = time_preference

    if any(word in lowered for word in ["book", "schedule", "confirm"]):
        memory["last_intent"] = "book"
    elif any(word in lowered for word in ["availability", "available", "slot", "slots"]):
        memory["last_intent"] = "availability"
    elif any(word in lowered for word in ["cancel", "delete", "remove"]):
        memory["last_intent"] = "cancel"
    elif any(word in lowered for word in ["reschedule", "change", "move"]):
        memory["last_intent"] = "reschedule"
    elif any(word in lowered for word in ["summary", "patients", "appointments", "fever"]):
        memory["last_intent"] = "summary"

    persist_memory(db, session_primary_id, memory)
    return memory


def update_memory_from_tool_calls(
    db: Session,
    session_primary_id: int,
    tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    memory = load_memory(db, session_primary_id)
    for tool_call in tool_calls or []:
        tool_name = tool_call.get("tool")
        result = tool_call.get("result", {}) or {}
        arguments = tool_call.get("arguments", {}) or {}

        if arguments.get("doctor_name"):
            memory["selected_doctor"] = arguments["doctor_name"]
        if arguments.get("date_str"):
            memory["requested_date"] = arguments["date_str"]
        if arguments.get("start_time_str"):
            memory["requested_time"] = arguments["start_time_str"]
        if arguments.get("patient_name"):
            memory["patient_name"] = arguments["patient_name"]
        if arguments.get("patient_email"):
            memory["patient_email"] = arguments["patient_email"]

        if tool_name == "check_availability":
            memory["last_available_slots"] = result.get("available_slots", [])
        elif tool_name == "create_appointment" and result.get("success"):
            memory["last_appointment"] = result
            memory["last_appointment_id"] = result.get("appointment_id")
            memory["active_appointments"] = [result]
            memory["last_available_slots"] = []
        elif tool_name == "list_patient_appointments":
            memory["active_appointments"] = result.get("appointments", [])
            if result.get("appointments"):
                memory["last_appointment"] = result["appointments"][0]
                memory["last_appointment_id"] = result["appointments"][0].get("appointment_id")
        elif tool_name == "cancel_appointment" and result.get("success"):
            appointment = result.get("appointment")
            memory["last_appointment"] = appointment
            memory["last_appointment_id"] = appointment.get("appointment_id") if appointment else None
            memory["active_appointments"] = [
                appt for appt in memory.get("active_appointments", [])
                if appt.get("appointment_id") != memory["last_appointment_id"]
            ]
        elif tool_name == "reschedule_appointment" and result.get("success"):
            appointment = result.get("appointment")
            memory["last_appointment"] = appointment
            memory["last_appointment_id"] = appointment.get("appointment_id") if appointment else None
        elif tool_name == "reschedule_appointment" and result.get("alternative_slots"):
            memory["last_available_slots"] = result.get("alternative_slots", [])

    persist_memory(db, session_primary_id, memory)
    return memory


def build_memory_context(memory: dict[str, Any]) -> str:
    summary = _summarize(memory)
    if not summary:
        return "No structured memory recorded yet."
    return summary
