"""LLM orchestration and deterministic demo-mode agent behavior."""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from app.agent_memory import build_memory_context
from app.mcp_client import call_tool as call_mcp_protocol_tool
from app.mcp_client import get_legacy_tools_metadata

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "demo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")


def _get_tools_for_openai() -> list:
    meta = _fetch_tools_metadata()
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in meta
    ]


def _fetch_tools_metadata() -> list:
    try:
        return get_legacy_tools_metadata(BASE_URL)
    except Exception:
        return []


def _call_tool(tool_name: str, arguments: dict, db=None) -> Any:
    try:
        return call_mcp_protocol_tool(tool_name, arguments)
    except Exception as exc:
        return {"error": str(exc)}


def build_messages_from_history(db, session_primary_id: int, last_n: int = 12) -> list:
    from app.models import PromptHistory

    history = (
        db.query(PromptHistory)
        .filter(PromptHistory.session_id == session_primary_id)
        .order_by(PromptHistory.created_at.desc())
        .limit(last_n)
        .all()
    )
    history = list(reversed(history))

    messages = []
    for item in history:
        if item.role == "user":
            messages.append({"role": "user", "content": item.content})
        elif item.role == "assistant":
            content = item.content
            if item.tool_calls:
                try:
                    tool_calls = json.loads(item.tool_calls)
                except json.JSONDecodeError:
                    tool_calls = []
                if tool_calls:
                    tool_summaries = []
                    for tool_call in tool_calls:
                        result = tool_call.get("result", {})
                        if tool_call.get("tool") == "check_availability":
                            tool_summaries.append(
                                f"check_availability returned {len(result.get('available_slots', []))} slots"
                            )
                        elif tool_call.get("tool") in {"create_appointment", "reschedule_appointment"} and result.get("success"):
                            tool_summaries.append(
                                f"{tool_call.get('tool')} confirmed appointment #{result.get('appointment_id') or result.get('appointment', {}).get('appointment_id')}"
                            )
                        elif tool_call.get("tool") == "cancel_appointment" and result.get("success"):
                            tool_summaries.append("cancel_appointment succeeded")
                        elif tool_call.get("tool") == "query_stats":
                            tool_summaries.append(
                                f"query_stats found {result.get('total_appointments', 0)} appointments"
                            )
                    if tool_summaries:
                        content += "\n[Tool memory] " + "; ".join(tool_summaries)
            messages.append({"role": "assistant", "content": content})
    return messages


def _get_system_prompt(memory_context: Optional[str] = None) -> str:
    tools = json.dumps(_fetch_tools_metadata(), indent=2)
    prompt = (
        "You are a medical appointment assistant that can discover and call MCP tools.\n"
        "Use check_availability before create_appointment when the user asks to book.\n"
        "Use query_stats for doctor reporting and send_notification for doctor delivery.\n"
        f"Available tools:\n{tools}"
    )
    if memory_context:
        prompt += f"\nStructured session memory:\n{memory_context}"
    return prompt


def _extract_email(text: str) -> Optional[str]:
    match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text or "")
    return match.group(0) if match else None


def _extract_name(text: str) -> Optional[str]:
    patterns = [
        r"(?:my name is|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"for\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_slot_id(text: str) -> Optional[int]:
    match = re.search(r"\bslot\s+(\d+)\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _extract_appointment_id(text: str) -> Optional[int]:
    patterns = [
        r"\bappointment\s+(\d+)\b",
        r"\bbooking\s+(\d+)\b",
        r"\bid\s+(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_relative_choice(text: str) -> Optional[int]:
    lowered = (text or "").lower()
    mapping = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
        "last": -1,
    }
    for key, value in mapping.items():
        if key in lowered:
            return value
    if any(token in lowered for token in ["earliest", "next available", "book it", "book that", "book this"]):
        return 0
    return None


def _extract_time(text: str) -> Optional[str]:
    explicit = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if explicit:
        return f"{int(explicit.group(1)):02d}:{explicit.group(2)}"

    am_pm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE)
    if am_pm:
        hour = int(am_pm.group(1))
        minute = int(am_pm.group(2) or "0")
        suffix = am_pm.group(3).lower()
        if suffix == "pm" and hour != 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    return None


def _resolve_date(text: str) -> str:
    lowered = (text or "").lower()
    now = datetime.now()

    if "today" in lowered:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for day_name, weekday_index in weekdays.items():
        if day_name in lowered:
            target = now
            while target.weekday() != weekday_index:
                target += timedelta(days=1)
            if target.date() == now.date():
                target += timedelta(days=7)
            return target.strftime("%Y-%m-%d")

    return (now + timedelta(days=1)).strftime("%Y-%m-%d")


def _resolve_doctor_name(text: str, messages: list[dict]) -> str:
    combined = " ".join(
        [m.get("content", "") for m in messages if m.get("role") in {"user", "assistant"}]
    )
    haystack = f"{combined} {text}".lower()
    if "smith" in haystack:
        return "Dr. Smith"
    return "Dr. Ahuja"


def _latest_user_context(messages: list[dict]) -> dict[str, Any]:
    context = {"email": None, "name": None, "doctor": None, "date_str": None}
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        context["email"] = _extract_email(content) or context["email"]
        context["name"] = _extract_name(content) or context["name"]
        if "dr." in content.lower() or "doctor" in content.lower():
            context["doctor"] = _resolve_doctor_name(content, messages)
        if any(word in content.lower() for word in ["today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
            context["date_str"] = _resolve_date(content)
    return context


def _merge_memory_context(memory_state: Optional[dict[str, Any]], message_context: dict[str, Any]) -> dict[str, Any]:
    memory_state = memory_state or {}
    return {
        "email": message_context.get("email") or memory_state.get("patient_email"),
        "name": message_context.get("name") or memory_state.get("patient_name"),
        "doctor": message_context.get("doctor") or memory_state.get("selected_doctor"),
        "date_str": message_context.get("date_str") or memory_state.get("requested_date"),
        "requested_time": memory_state.get("requested_time"),
        "last_available_slots": memory_state.get("last_available_slots", []),
        "last_appointment_id": memory_state.get("last_appointment_id"),
        "active_appointments": memory_state.get("active_appointments", []),
        "time_preference": memory_state.get("time_preference"),
    }


def get_llm_response(
    messages: list,
    db=None,
    patient_context: Optional[dict] = None,
    memory_state: Optional[dict[str, Any]] = None,
) -> tuple[str, list]:
    if LLM_PROVIDER == "demo":
        return _demo_mode_response(messages, db, patient_context or {}, memory_state or {})
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_response(messages, db, memory_state)
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return _anthropic_response(messages, db, memory_state)
    if LLM_PROVIDER == "local":
        return _local_llm_response(messages, db, memory_state)
    return _demo_mode_response(messages, db, patient_context or {}, memory_state or {})


def _demo_mode_response(
    messages: list,
    db=None,
    patient_context: Optional[dict] = None,
    memory_state: Optional[dict[str, Any]] = None,
) -> tuple[str, list]:
    patient_context = patient_context or {}
    memory_state = memory_state or {}
    user_content = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_content = message.get("content", "")
            break

    lower = user_content.lower()
    tool_calls: list[dict[str, Any]] = []
    context = _merge_memory_context(memory_state, _latest_user_context(messages))
    doctor_name = context["doctor"] or _resolve_doctor_name(user_content, messages)
    date_str = context["date_str"] or _resolve_date(user_content)
    patient_email = (
        patient_context.get("patient_email")
        or _extract_email(user_content)
        or context["email"]
        or "patient@demo.local"
    )
    patient_name = (
        patient_context.get("patient_name")
        or _extract_name(user_content)
        or context["name"]
        or "Guest Patient"
    )

    wants_booking = any(word in lower for word in ["book", "schedule", "confirm"])
    wants_cancel = any(word in lower for word in ["cancel", "delete", "remove"])
    wants_change = any(word in lower for word in ["reschedule", "change", "move"])
    wants_doctors = any(word in lower for word in ["doctor options", "available doctors", "list doctors", "which doctors"])
    slot_id = _extract_slot_id(user_content)
    appointment_id = _extract_appointment_id(user_content)
    time_str = _extract_time(user_content)
    relative_choice = _extract_relative_choice(user_content)

    if slot_id is None and time_str is None and relative_choice is not None and context["last_available_slots"]:
        try:
            slot = context["last_available_slots"][relative_choice]
            slot_id = slot.get("slot_id")
            doctor_name = slot.get("doctor") or doctor_name
            date_str = slot.get("date") or date_str
        except IndexError:
            pass

    if appointment_id is None and len(context["active_appointments"]) == 1:
        appointment_id = context["active_appointments"][0].get("appointment_id")

    if wants_doctors:
        doctors_result = _call_tool("list_doctors", {}, db)
        tool_calls.append(
            {
                "tool": "list_doctors",
                "arguments": {},
                "result": doctors_result,
            }
        )
        doctors = doctors_result.get("doctors", [])
        if not doctors:
            return "No doctors are available right now.", tool_calls
        lines = [
            f"{doctor['name']} ({doctor['specialization']})"
            for doctor in doctors
        ]
        return "You can book with:\n" + "\n".join(lines), tool_calls

    if wants_cancel and appointment_id is not None:
        cancel_args = {
            "appointment_id": appointment_id,
            "patient_email": patient_email,
        }
        cancel_result = _call_tool("cancel_appointment", cancel_args, db)
        tool_calls.append(
            {
                "tool": "cancel_appointment",
                "arguments": cancel_args,
                "result": cancel_result,
            }
        )
        if cancel_result.get("success"):
            return f"Appointment {appointment_id} has been cancelled.", tool_calls
        return cancel_result.get("error", "Unable to cancel that appointment."), tool_calls

    if wants_change and appointment_id is not None and (slot_id is not None or time_str):
        reschedule_args = {
            "appointment_id": appointment_id,
            "patient_email": patient_email,
            "doctor_name": doctor_name,
        }
        if slot_id is not None:
            reschedule_args["new_slot_id"] = slot_id
        if time_str:
            reschedule_args["date_str"] = date_str
            reschedule_args["start_time_str"] = time_str
        reschedule_result = _call_tool("reschedule_appointment", reschedule_args, db)
        tool_calls.append(
            {
                "tool": "reschedule_appointment",
                "arguments": reschedule_args,
                "result": reschedule_result,
            }
        )
        if reschedule_result.get("success"):
            appointment = reschedule_result["appointment"]
            return (
                f"Appointment {appointment['appointment_id']} was moved to "
                f"{appointment['doctor']} on {appointment['date']} at {appointment['start_time']}.",
                tool_calls,
            )
        return reschedule_result.get("error", "Unable to change that appointment."), tool_calls

    if wants_booking and (slot_id is not None or time_str):
        booking_args = {
            "doctor_name": doctor_name,
            "patient_name": patient_name,
            "patient_email": patient_email,
        }
        if slot_id is not None:
            booking_args["slot_id"] = slot_id
        if time_str:
            booking_args["date_str"] = date_str
            booking_args["start_time_str"] = time_str

        booking_result = _call_tool("create_appointment", booking_args, db)
        tool_calls.append(
            {
                "tool": "create_appointment",
                "arguments": booking_args,
                "result": booking_result,
            }
        )

        if booking_result.get("success"):
            return (
                f"Appointment confirmed for {booking_result['patient']} with {booking_result['doctor']} "
                f"on {booking_result['date']} at {booking_result['start_time']}. "
                f"A confirmation was sent to {booking_result['patient_email']}.",
                tool_calls,
            )
        return booking_result.get("error", "Booking failed."), tool_calls

    wants_availability = any(
        word in lower
        for word in ["availability", "available", "slot", "slots", "tomorrow", "today", "morning", "afternoon"]
    ) or ("appointment" in lower and not wants_booking)

    if wants_availability:
        result = _call_tool(
            "check_availability",
            {"doctor_name": doctor_name, "date_str": date_str},
            db,
        )
        tool_calls.append(
            {
                "tool": "check_availability",
                "arguments": {"doctor_name": doctor_name, "date_str": date_str},
                "result": result,
            }
        )
        slots = result.get("available_slots", [])
        if not slots:
            return result.get("error") or f"No available slots found for {doctor_name} on {date_str}.", tool_calls

        if "morning" in lower or context.get("time_preference") == "morning":
            slots = [slot for slot in slots if slot["start_time"] < "12:00"] or slots
        elif "afternoon" in lower or context.get("time_preference") == "afternoon":
            slots = [slot for slot in slots if slot["start_time"] >= "12:00"] or slots

        slot_lines = [
            f"Slot {slot['slot_id']}: {slot['start_time']} - {slot['end_time']}"
            for slot in slots[:6]
        ]
        return (
            f"Available slots for {doctor_name} on {date_str}:\n"
            + "\n".join(slot_lines)
            + "\nReply with a slot number like 'Book slot 10' or a time like 'Book the 9:00 AM slot'.",
            tool_calls,
        )

    return (
        "I can help you check availability, book an appointment, and generate doctor summaries. "
        "Try 'Show Dr. Ahuja availability for tomorrow morning' or 'Book slot 10'.",
        [],
    )


def _openai_response(messages: list, db=None, memory_state: Optional[dict[str, Any]] = None) -> tuple[str, list]:
    """Use OpenAI API with function calling."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_content = _get_system_prompt(build_memory_context(memory_state or {}))
    msgs = [{"role": "system", "content": system_content}] + [
        {"role": m["role"], "content": m.get("content", "")} for m in messages
    ]
    tools = _get_tools_for_openai()
    tool_calls_made = []

    max_rounds = 5
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=msgs,
            tools=tools if tools else None,
        )
        choice = response.choices[0]
        msg = choice.message

        if msg.tool_calls:
            msgs.append(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                result = _call_tool(name, args, db)
                tool_calls_made.append({"tool": name, "arguments": args, "result": result})
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
            continue

        return (msg.content or ""), tool_calls_made

    return "I couldn't complete the request.", tool_calls_made


def _anthropic_response(messages: list, db=None, memory_state: Optional[dict[str, Any]] = None) -> tuple[str, list]:
    """Use Anthropic Claude with tool use."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_content = _get_system_prompt(build_memory_context(memory_state or {}))
    msgs = [{"role": m["role"], "content": m.get("content", "")} for m in messages]
    tools = []
    for t in _fetch_tools_metadata():
        tools.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        })
    tool_calls_made = []

    max_rounds = 5
    for _ in range(max_rounds):
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            max_tokens=1024,
            system=system_content,
            messages=msgs,
            tools=tools if tools else None,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    return block.text, tool_calls_made

        tool_use_blocks = [b for b in response.content if hasattr(b, "id") and getattr(b, "name", None)]
        if not tool_use_blocks:
            return "No response.", tool_calls_made

        msgs.append({"role": "assistant", "content": response.content})
        for block in tool_use_blocks:
            name = getattr(block, "name", None)
            if name:
                args = getattr(block, "input", {}) or {}
                result = _call_tool(name, args, db)
                tool_calls_made.append({"tool": name, "arguments": args, "result": result})
                msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }],
                })
        msgs = msgs  # next iteration

    return "Could not complete.", tool_calls_made


def _local_llm_response(messages: list, db=None, memory_state: Optional[dict[str, Any]] = None) -> tuple[str, list]:
    """Use local LLM via HTTP (e.g. Ollama-compatible)."""
    import httpx

    system_content = _get_system_prompt(build_memory_context(memory_state or {}))
    msgs = [{"role": "system", "content": system_content}] + [
        {"role": m["role"], "content": m.get("content", "")} for m in messages
    ]
    try:
        r = httpx.post(
            f"{LOCAL_LLM_URL}/chat/completions",
            json={
                "model": os.getenv("LOCAL_MODEL", "llama2"),
                "messages": msgs,
            },
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content or "No response.", []
    except Exception:
        pass
    return _demo_mode_response(messages, db, {}, memory_state or {})
