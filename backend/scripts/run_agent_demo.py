#!/usr/bin/env python3
"""
Example agent orchestration script.
Demonstrates a single conversation with the MCP server using the LLM.
- Reads /mcp/tools to discover tools
- Uses system prompt explaining tools
- Sends user message: "I want to book an appointment with Dr. Ahuja tomorrow morning"
- Handles function/tool calls from LLM and returns final text output.

Usage:
  Ensure backend is running (uvicorn or docker-compose). Then:
  cd backend && python scripts/run_agent_demo.py

  Or with OPENAI_API_KEY set:
  LLM_PROVIDER=openai OPENAI_API_KEY=sk-xxx python scripts/run_agent_demo.py
"""
import os
import sys
import json
import httpx

# Add parent to path for imports when run as script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "demo")
USER_MESSAGE = "I want to book an appointment with Dr. Ahuja tomorrow morning"


def fetch_tools():
    """Discover MCP tools from registry."""
    r = httpx.get(f"{BASE_URL}/mcp/tools", timeout=10)
    r.raise_for_status()
    return r.json()


def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call MCP tool via POST."""
    r = httpx.post(
        f"{BASE_URL}/mcp/tools/{tool_name}/call",
        json=arguments,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def run_demo_mode():
    """Demo mode: use /api/chat to get response (backend handles tool orchestration)."""
    r = httpx.post(
        f"{BASE_URL}/api/chat",
        json={"session_id": "agent_demo_session", "message": USER_MESSAGE},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("response", ""), data.get("tool_calls", [])


def run_openai_mode():
    """Use OpenAI API with tool calling."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    tools_meta = fetch_tools()
    functions = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools_meta
    ]
    system_prompt = f"""You are a medical appointment assistant. You help patients book appointments.
Available tools: {json.dumps([t['name'] for t in tools_meta])}
Use check_availability first, then create_appointment with slot_id from results.
Resolve "tomorrow" to actual YYYY-MM-DD date."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": USER_MESSAGE},
    ]
    max_rounds = 5
    for _ in range(max_rounds):
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
            tools=functions,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                result = call_tool(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
            continue
        return msg.content or "", []
    return "Max rounds exceeded.", []


def run_anthropic_mode():
    """Use Anthropic Claude with tool use."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    tools_meta = fetch_tools()
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in tools_meta]
    system = f"Medical appointment assistant. Tools: {[t['name'] for t in tools_meta]}. Use check_availability then create_appointment."
    messages = [{"role": "user", "content": USER_MESSAGE}]
    for _ in range(5):
        resp = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=tools,
        )
        if resp.stop_reason == "end_turn":
            for b in resp.content:
                if hasattr(b, "text") and b.text:
                    return b.text, []
        tool_blocks = [b for b in resp.content if hasattr(b, "name")]
        if not tool_blocks:
            return "No response", []
        messages.append({"role": "assistant", "content": resp.content})
        for b in tool_blocks:
            args = getattr(b, "input", {}) or {}
            result = call_tool(b.name, args)
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(result)}],
            })
    return "Max rounds exceeded.", []


def main():
    print("=" * 60)
    print("Agentic Appointment MCP - Agent Demo")
    print("=" * 60)
    print(f"BASE_URL: {BASE_URL}")
    print(f"LLM_PROVIDER: {LLM_PROVIDER}")
    print(f"User message: {USER_MESSAGE}")
    print()

    # Discover tools
    try:
        tools = fetch_tools()
        print(f"Discovered {len(tools)} tools: {[t['name'] for t in tools]}")
    except Exception as e:
        print(f"ERROR: Could not fetch tools. Is the backend running? {e}")
        sys.exit(1)
    print()

    if LLM_PROVIDER == "openai" and os.getenv("OPENAI_API_KEY"):
        print("Using OpenAI...")
        output, tool_calls = run_openai_mode()
    elif LLM_PROVIDER == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        print("Using Anthropic Claude...")
        output, tool_calls = run_anthropic_mode()
    else:
        print("Using demo mode (backend /api/chat)...")
        output, tool_calls = run_demo_mode()

    print()
    print("--- Final output ---")
    print(output)
    if tool_calls:
        print()
        print("--- Tool calls made ---")
        for tc in tool_calls:
            print(f"  - {tc.get('tool', tc)}: {tc.get('result', tc)}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
