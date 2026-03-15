"""
MCP tool registry.
Exposes tool metadata at /mcp/tools for LLM agent discovery.
Note: We implement a small custom registry rather than fastapi_mcp - no external MCP package used.
"""
from typing import Any

BASE_URL = "http://localhost:8000"  # Overridden by app when mounting


def get_tools_metadata(base_url: str = BASE_URL) -> list[dict[str, Any]]:
    """Return MCP tool metadata with input/output schemas and call URL."""
    return [
        {
            "name": "list_doctors",
            "description": "List all doctors with specialization and next available slot information.",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "doctors": {"type": "array", "items": {"type": "object"}},
                },
            },
            "call_url": f"{base_url}/mcp/tools/list_doctors/call",
        },
        {
            "name": "check_availability",
            "description": "Check available appointment slots for a doctor on a given date. Returns list of available time slots.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string", "description": "Doctor's name (e.g., 'Dr. Ahuja')"},
                    "date_str": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                },
                "required": ["doctor_name", "date_str"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "available_slots": {"type": "array", "items": {"type": "object"}},
                    "doctor": {"type": "string"},
                    "error": {"type": "string"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/check_availability/call",
        },
        {
            "name": "create_appointment",
            "description": "Create an appointment for a patient with a doctor. Requires patient details and either slot_id or date_str+start_time_str.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string"},
                    "patient_name": {"type": "string"},
                    "patient_email": {"type": "string"},
                    "slot_id": {"type": "integer", "description": "ID of the slot from check_availability"},
                    "date_str": {"type": "string", "description": "YYYY-MM-DD if not using slot_id"},
                    "start_time_str": {"type": "string", "description": "HH:MM if not using slot_id"},
                    "symptom": {"type": "string", "default": "general"},
                },
                "required": ["doctor_name", "patient_name", "patient_email"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "appointment_id": {"type": "integer"},
                    "doctor": {"type": "string"},
                    "patient": {"type": "string"},
                    "date": {"type": "string"},
                    "start_time": {"type": "string"},
                    "calendar_event_id": {"type": "string"},
                    "email_sent": {"type": "boolean"},
                    "alternative_slots": {"type": "array", "items": {"type": "object"}},
                    "error": {"type": "string"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/create_appointment/call",
        },
        {
            "name": "query_stats",
            "description": "Query appointment statistics between dates with optional doctor and symptom filters.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "symptom_filter": {"type": "string", "description": "e.g. 'fever'"},
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "total_appointments": {"type": "integer"},
                    "by_date": {"type": "object"},
                    "symptom_filter": {"type": "string"},
                    "symptoms": {"type": "object"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/query_stats/call",
        },
        {
            "name": "send_notification",
            "description": "Send a notification to a recipient via Slack or in-app notification.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "message": {"type": "string"},
                    "channel": {"type": "string", "default": "slack"},
                },
                "required": ["recipient", "message"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "channel": {"type": "string"},
                    "notification_id": {"type": "integer"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/send_notification/call",
        },
        {
            "name": "list_patient_appointments",
            "description": "Return the current patient's appointments for self-service management.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "patient_email": {"type": "string"},
                },
                "required": ["patient_email"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "appointments": {"type": "array", "items": {"type": "object"}},
                    "patient": {"type": "string"},
                    "patient_email": {"type": "string"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/list_patient_appointments/call",
        },
        {
            "name": "cancel_appointment",
            "description": "Cancel an existing patient appointment and release the booked slot.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer"},
                    "patient_email": {"type": "string"},
                },
                "required": ["appointment_id", "patient_email"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "message": {"type": "string"},
                    "appointment": {"type": "object"},
                    "error": {"type": "string"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/cancel_appointment/call",
        },
        {
            "name": "reschedule_appointment",
            "description": "Move an existing patient appointment to a different doctor slot.",
            "input_schema": {
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
            "output_schema": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "message": {"type": "string"},
                    "appointment": {"type": "object"},
                    "alternative_slots": {"type": "array", "items": {"type": "object"}},
                    "error": {"type": "string"},
                },
            },
            "call_url": f"{base_url}/mcp/tools/reschedule_appointment/call",
        },
    ]
