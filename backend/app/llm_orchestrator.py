"""LLM orchestration and deterministic demo-mode agent behavior."""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

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
        from app.mcp_registry import get_tools_metadata

        return get_tools_metadata(BASE_URL)
    except Exception:
        pass

    try:
        response = httpx.get(f"{BASE_URL}/mcp/tools", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass

    return []


def _call_tool(tool_name: str, arguments: dict, db=None) -> Any:
    if db is not None:
        try:
            from app.tools import check_availability, create_appointment, query_stats, send_notification

            handlers = {
                "check_availability": lambda: check_availability(
                    db, arguments.get("doctor_name", ""), arguments.get("date_str", "")
                ),
                "create_appointment": lambda: create_appointment(
                    db,
                    arguments.get("doctor_name", ""),
                    arguments.get("patient_name", ""),
                    arguments.get("patient_email", ""),
                    slot_id=arguments.get("slot_id"),
                    date_str=arguments.get("date_str"),
                    start_time_str=arguments.get("start_time_str"),
                    symptom=arguments.get("symptom", "general"),
                ),
                "query_stats": lambda: query_stats(
                    db,
                    doctor_name=arguments.get("doctor_name"),
                    start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"),
                    symptom_filter=arguments.get("symptom_filter"),
                ),
                "send_notification": lambda: send_notification(
                    db,
                    arguments.get("recipient", ""),
                    arguments.get("message", ""),
                    arguments.get("channel", "slack"),
                ),
            }
            if tool_name in handlers:
                return handlers[tool_name]()
        except Exception as exc:
            return {"error": str(exc)}

    try:
        response = httpx.post(
            f"{BASE_URL}/mcp/tools/{tool_name}/call",
            json=arguments,
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        return {"error": response.text}
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
            messages.append({"role": "assistant", "content": item.content})
    return messages


def _get_system_prompt() -> str:
    tools = json.dumps(_fetch_tools_metadata(), indent=2)
    return (
        "You are a medical appointment assistant that can discover and call MCP tools.\n"
        "Use check_availability before create_appointment when the user asks to book.\n"
        "Use query_stats for doctor reporting and send_notification for doctor delivery.\n"
        f"Available tools:\n{tools}"
    )


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


def get_llm_response(messages: list, db=None, patient_context: Optional[dict] = None) -> tuple[str, list]:
    if LLM_PROVIDER == "demo":
        return _demo_mode_response(messages, db, patient_context or {})
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_response(messages, db)
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return _anthropic_response(messages, db)
    if LLM_PROVIDER == "local":
        return _local_llm_response(messages, db)
    return _demo_mode_response(messages, db, patient_context or {})


def _demo_mode_response(messages: list, db=None, patient_context: Optional[dict] = None) -> tuple[str, list]:
    patient_context = patient_context or {}
    user_content = ""
    for message in reversed(messages):
        if message.get("role") == "user":
            user_content = message.get("content", "")
            break

    lower = user_content.lower()
    tool_calls: list[dict[str, Any]] = []
    context = _latest_user_context(messages)
    doctor_name = _resolve_doctor_name(user_content, messages)
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
    slot_id = _extract_slot_id(user_content)
    time_str = _extract_time(user_content)

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

        if "morning" in lower:
            slots = [slot for slot in slots if slot["start_time"] < "12:00"] or slots
        elif "afternoon" in lower:
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


def _openai_response(messages: list, db=None) -> tuple[str, list]:
    """Use OpenAI API with function calling."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_content = _get_system_prompt()
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


def _anthropic_response(messages: list, db=None) -> tuple[str, list]:
    """Use Anthropic Claude with tool use."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_content = _get_system_prompt()
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


def _local_llm_response(messages: list, db=None) -> tuple[str, list]:
    """Use local LLM via HTTP (e.g. Ollama-compatible)."""
    system_content = _get_system_prompt()
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
    return _demo_mode_response(messages, db)
