"""Shared tool dispatch used by the MCP server and compatibility APIs."""
from typing import Any

from sqlalchemy.orm import Session

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


def get_tool_handlers() -> dict[str, Any]:
    return {
        "list_doctors": lambda db, data: list_doctors(db),
        "check_availability": lambda db, data: check_availability(
            db,
            data.get("doctor_name", ""),
            data.get("date_str", ""),
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


def execute_tool(tool_name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    handlers = get_tool_handlers()
    if tool_name not in handlers:
        return {"success": False, "error": f"Tool '{tool_name}' not found."}
    return handlers[tool_name](db, arguments)
