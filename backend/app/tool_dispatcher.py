"""Shared tool dispatch used by the MCP server and compatibility APIs."""
from typing import Any

from sqlalchemy.orm import Session

from app.mcp_tool_registry import registry
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


@registry.register(
    name="list_doctors",
    description="List all doctors with specialization and next available slot information.",
    input_schema={"type": "object", "properties": {}},
    output_schema={"type": "object", "properties": {"doctors": {"type": "array", "items": {"type": "object"}}}},
)
def handle_list_doctors(db: Session, _: dict[str, Any]) -> dict[str, Any]:
    return list_doctors(db)


@registry.register(
    name="check_availability",
    description="Check available appointment slots for a doctor on a given date. Returns list of available time slots.",
    input_schema={
        "type": "object",
        "properties": {
            "doctor_name": {"type": "string", "description": "Doctor name"},
            "date_str": {"type": "string", "description": "Date in YYYY-MM-DD format"},
        },
        "required": ["doctor_name", "date_str"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "available_slots": {"type": "array", "items": {"type": "object"}},
            "doctor": {"type": "string"},
            "error": {"type": "string"},
        },
    },
)
def handle_check_availability(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return check_availability(
        db,
        data.get("doctor_name", ""),
        data.get("date_str", ""),
    )


@registry.register(
    name="create_appointment",
    description="Create an appointment for a patient with a doctor. Requires patient details and either slot_id or date_str plus start_time_str.",
    input_schema={
        "type": "object",
        "properties": {
            "doctor_name": {"type": "string"},
            "patient_name": {"type": "string"},
            "patient_email": {"type": "string"},
            "slot_id": {"type": "integer"},
            "date_str": {"type": "string"},
            "start_time_str": {"type": "string"},
            "symptom": {"type": "string", "default": "general"},
        },
        "required": ["doctor_name", "patient_name", "patient_email"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "appointment_id": {"type": "integer"},
            "doctor": {"type": "string"},
            "patient": {"type": "string"},
            "patient_email": {"type": "string"},
            "date": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "calendar_event_id": {"type": "string"},
            "email_sent": {"type": "boolean"},
            "alternative_slots": {"type": "array", "items": {"type": "object"}},
            "error": {"type": "string"},
        },
    },
)
def handle_create_appointment(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return create_appointment(
        db,
        data.get("doctor_name", ""),
        data.get("patient_name", ""),
        data.get("patient_email", ""),
        slot_id=data.get("slot_id"),
        date_str=data.get("date_str"),
        start_time_str=data.get("start_time_str"),
        symptom=data.get("symptom", "general"),
    )


@registry.register(
    name="query_stats",
    description="Query appointment statistics between dates with optional doctor and symptom filters.",
    input_schema={
        "type": "object",
        "properties": {
            "doctor_name": {"type": "string"},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "symptom_filter": {"type": "string"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "total_appointments": {"type": "integer"},
            "by_date": {"type": "object"},
            "symptom_filter": {"type": "string"},
            "symptoms": {"type": "object"},
        },
    },
)
def handle_query_stats(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return query_stats(
        db,
        doctor_name=data.get("doctor_name"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        symptom_filter=data.get("symptom_filter"),
    )


@registry.register(
    name="send_notification",
    description="Send a notification to a recipient via Slack or in-app notification.",
    input_schema={
        "type": "object",
        "properties": {
            "recipient": {"type": "string"},
            "message": {"type": "string"},
            "channel": {"type": "string", "default": "slack"},
        },
        "required": ["recipient", "message"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "channel": {"type": "string"},
            "notification_id": {"type": "integer"},
        },
    },
)
def handle_send_notification(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return send_notification(
        db,
        data.get("recipient", ""),
        data.get("message", ""),
        data.get("channel", "slack"),
    )


@registry.register(
    name="list_patient_appointments",
    description="Return the current patient's appointments for self-service management.",
    input_schema={
        "type": "object",
        "properties": {"patient_email": {"type": "string"}},
        "required": ["patient_email"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "appointments": {"type": "array", "items": {"type": "object"}},
            "patient": {"type": "string"},
            "patient_email": {"type": "string"},
        },
    },
)
def handle_list_patient_appointments(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return list_patient_appointments(
        db,
        data.get("patient_email", ""),
    )


@registry.register(
    name="cancel_appointment",
    description="Cancel an existing patient appointment and release the booked slot.",
    input_schema={
        "type": "object",
        "properties": {
            "appointment_id": {"type": "integer"},
            "patient_email": {"type": "string"},
        },
        "required": ["appointment_id", "patient_email"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message": {"type": "string"},
            "appointment": {"type": "object"},
            "error": {"type": "string"},
        },
    },
)
def handle_cancel_appointment(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return cancel_appointment(
        db,
        data.get("appointment_id"),
        data.get("patient_email", ""),
    )


@registry.register(
    name="reschedule_appointment",
    description="Move an existing patient appointment to a different doctor slot.",
    input_schema={
        "type": "object",
        "properties": {
            "appointment_id": {"type": "integer"},
            "patient_email": {"type": "string"},
            "doctor_name": {"type": "string"},
            "new_slot_id": {"type": "integer"},
            "date_str": {"type": "string"},
            "start_time_str": {"type": "string"},
        },
        "required": ["appointment_id", "patient_email"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message": {"type": "string"},
            "appointment": {"type": "object"},
            "alternative_slots": {"type": "array", "items": {"type": "object"}},
            "error": {"type": "string"},
        },
    },
)
def handle_reschedule_appointment(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    return reschedule_appointment(
        db,
        data.get("appointment_id"),
        data.get("patient_email", ""),
        new_slot_id=data.get("new_slot_id") or data.get("slot_id"),
        doctor_name=data.get("doctor_name"),
        date_str=data.get("date_str"),
        start_time_str=data.get("start_time_str"),
    )


def execute_tool(tool_name: str, arguments: dict[str, Any], db: Session) -> dict[str, Any]:
    return registry.call(tool_name, arguments, db)
