"""
LLM orchestration with tool calling. Supports OpenAI, Claude, and demo mode.
When LLM_PROVIDER=local, uses HTTP endpoint. Otherwise uses OpenAI or Claude.
"""
import os
import json
import httpx
from typing import Any

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "demo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434/v1")


def _get_tools_for_openai() -> list:
    """Format MCP tools as OpenAI function schema."""
    meta = _fetch_tools_metadata()
    functions = []
    for t in meta:
        functions.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        })
    return functions


def _fetch_tools_metadata() -> list:
    """Fetch tools from MCP registry. Use local import when in-process to avoid self-request."""
    try:
        from app.mcp_registry import get_tools_metadata
        return get_tools_metadata(BASE_URL)
    except Exception:
        pass
    try:
        r = httpx.get(f"{BASE_URL}/mcp/tools", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def _call_tool(tool_name: str, arguments: dict, db=None) -> Any:
    """Call MCP tool via HTTP or direct invocation when db is provided (in-process)."""
    if db is not None:
        try:
            from app.tools import check_availability, create_appointment, query_stats, send_notification
            handlers = {
                "check_availability": lambda: check_availability(db, arguments.get("doctor_name", ""), arguments.get("date_str", "")),
                "create_appointment": lambda: create_appointment(db, arguments.get("doctor_name", ""), arguments.get("patient_name", ""),
                    arguments.get("patient_email", ""), slot_id=arguments.get("slot_id"), date_str=arguments.get("date_str"),
                    start_time_str=arguments.get("start_time_str"), symptom=arguments.get("symptom", "general")),
                "query_stats": lambda: query_stats(db, doctor_name=arguments.get("doctor_name"), start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"), symptom_filter=arguments.get("symptom_filter")),
                "send_notification": lambda: send_notification(db, arguments.get("recipient", ""), arguments.get("message", ""), arguments.get("channel", "slack")),
            }
            if tool_name in handlers:
                return handlers[tool_name]()
        except Exception as e:
            return {"error": str(e)}
    try:
        r = httpx.post(
            f"{BASE_URL}/mcp/tools/{tool_name}/call",
            json=arguments,
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": r.text}
    except Exception as e:
        return {"error": str(e)}


def build_messages_from_history(db, session_primary_id: int, last_n: int = 10) -> list:
    """Build message list from PromptHistory for context."""
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
    for h in history:
        if h.role == "user":
            messages.append({"role": "user", "content": h.content})
        elif h.role == "assistant":
            messages.append({"role": "assistant", "content": h.content})
    return messages


def _get_system_prompt() -> str:
    tools_desc = json.dumps(_fetch_tools_metadata(), indent=2)
    return f"""You are a medical appointment assistant. You help patients book appointments with doctors.

Available MCP tools (call POST /mcp/tools/{{name}}/call with JSON body):
{tools_desc}

Workflow:
1. For "check availability" - use check_availability with doctor_name and date_str (YYYY-MM-DD).
2. For "book appointment" - use create_appointment with doctor_name, patient_name, patient_email, and slot_id (from availability) or date_str+start_time_str.
3. For doctor stats - use query_stats.
4. For notifications - use send_notification.

If the user mentions "tomorrow", resolve to the actual date in YYYY-MM-DD.
Respond naturally and confirm bookings clearly."""


def get_llm_response(messages: list, db=None) -> tuple[str, list]:
    """
    Call LLM with tool support. Returns (final_text, list_of_tool_calls_made).
    In demo mode, uses rule-based tool invocation.
    """
    if LLM_PROVIDER == "demo":
        return _demo_mode_response(messages, db)
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return _openai_response(messages, db)
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return _anthropic_response(messages, db)
    if LLM_PROVIDER == "local":
        return _local_llm_response(messages, db)
    return _demo_mode_response(messages, db)


def _demo_mode_response(messages: list, db=None) -> tuple[str, list]:
    """
    Demo mode: parse user intent and call tools directly without real LLM.
    Simulates agentic flow for testing.
    """
    user_content = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_content = m.get("content", "")
            break

    lower = user_content.lower()
    tool_calls = []

    # Check intent: availability
    if "availability" in lower or "available" in lower or "slot" in lower or "book" in lower or "appointment" in lower:
        doctor_name = "Dr. Ahuja"
        if "dr." in lower or "doctor" in lower:
            for part in user_content.split():
                if part.lower().startswith("dr.") or (len(part) > 3 and part[0].isupper()):
                    if "ahuja" in part.lower() or "smith" in part.lower():
                        doctor_name = part if part.lower().startswith("dr.") else f"Dr. {part}"
        from datetime import datetime, timedelta
        date_str = ""
        if "tomorrow" in lower:
            date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "friday" in lower or "next friday" in lower:
            d = datetime.now()
            while d.weekday() != 4:
                d += timedelta(days=1)
            date_str = d.strftime("%Y-%m-%d")
        else:
            date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        result = _call_tool("check_availability", {"doctor_name": doctor_name, "date_str": date_str}, db)
        tool_calls.append({"tool": "check_availability", "arguments": {"doctor_name": doctor_name, "date_str": date_str}, "result": result})

        slots = result.get("available_slots", [])
        if slots:
            resp = f"Here are the available slots for {doctor_name} on {date_str}:\n"
            for s in slots[:5]:
                resp += f"- Slot {s['slot_id']}: {s['start_time']} - {s['end_time']}\n"
            resp += "\nTo book, say something like: 'Please book slot X' or 'Book the 9:00 AM slot' with your name and email."
        else:
            resp = result.get("error") or f"No available slots found for {doctor_name} on {date_str}."
        return resp, tool_calls

    # Check intent: book
    if "book" in lower and ("slot" in lower or any(c.isdigit() for c in user_content)):
        doctor_name = "Dr. Ahuja"
        slot_id = None
        for w in user_content.replace(",", " ").split():
            if w.isdigit():
                slot_id = int(w)
                break
        if not slot_id:
            return "Please specify which slot number to book (e.g. 'Book slot 1').", []

        # Extract name/email from context or use defaults for demo
        patient_name = "Demo Patient"
        patient_email = "demo@example.com"
        for line in messages:
            c = (line.get("content") or "")
            if "@" in c:
                for part in c.split():
                    if "@" in part and "." in part:
                        patient_email = part.strip(".,")
                        break
        result = _call_tool(
            "create_appointment",
            {
                "doctor_name": doctor_name,
                "patient_name": patient_name,
                "patient_email": patient_email,
                "slot_id": slot_id,
            },
            db,
        )
        tool_calls.append({
            "tool": "create_appointment",
            "arguments": {"doctor_name": doctor_name, "patient_name": patient_name, "patient_email": patient_email, "slot_id": slot_id},
            "result": result,
        })

        if result.get("success"):
            return (
                f"✓ Appointment confirmed! Dr. {result.get('doctor')} on {result.get('date')} "
                f"at {result.get('start_time')}. Confirmation email sent to {patient_email}.",
                tool_calls,
            )
        return result.get("error", "Booking failed."), tool_calls

    # Default
    return (
        "I can help you check doctor availability and book appointments. "
        "Try: 'Check Dr. Ahuja's availability for tomorrow' or 'Book an appointment with Dr. Ahuja tomorrow morning'.",
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
                result = _call_tool(name, args)
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
                result = _call_tool(name, args)
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
