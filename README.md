# Agentic Appointment MCP

A minimal full-stack demo implementing **Agentic AI with MCP** (Model Context Protocol). Allows patients to schedule doctor appointments via natural language and doctors to get smart summary reports. Uses FastAPI (backend), React (frontend), PostgreSQL, and MCP tools that an LLM agent can discover and invoke.

## Quick Start

### With Docker (Recommended)

```bash
docker-compose up
```

- **Backend**: http://localhost:8000  
- **Frontend**: http://localhost:3000  
- **API Docs**: http://localhost:8000/docs  

The DB is seeded automatically with 2 doctors (Dr. Ahuja, Dr. Smith) and sample slots.

### Local Setup

1. **PostgreSQL**  
   Create a database:
   ```bash
   createdb appointment_db
   ```

2. **Backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   cp ../.env.example ../.env   # optional
   python scripts/seed_db.py
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Frontend: http://localhost:5173

4. **Run agent demo script**
   ```bash
   cd backend
   python scripts/run_agent_demo.py
   ```

## Sample Prompts

### Scenario 1: Patient Appointment Scheduling

Copy and paste into the **Patient Chat**:

1. **Check availability**
   - *"I want to check Dr. Ahuja's availability for tomorrow afternoon"*
   - *"I want to book an appointment with Dr. Ahuja tomorrow morning"*

2. **Book a slot** (after availability is shown)
   - *"Please book slot 1"*
   - *"Book the 9:00 AM slot for John Doe, john@example.com"*

**Expected output (demo mode):**
- First message: List of available slots with slot IDs and times
- Second message: Confirmation with doctor, date, time, and email sent

### Scenario 2: Doctor Summary Report

1. Go to **Doctor Dashboard**
2. Enter doctor name (e.g., `Dr. Ahuja`)
3. Optional prompt: *"How many patients visited yesterday? Summarize today and tomorrow."*
4. Click **Get summary**

**Expected output:**
- Report with today, yesterday, tomorrow appointment counts
- Stats displayed in bullet format

## API Overview

| Endpoint | Description |
|----------|-------------|
| `GET /mcp/tools` | List MCP tools (metadata, schemas, call URLs) |
| `POST /mcp/tools/{tool_name}/call` | Invoke a tool (e.g. `check_availability`, `create_appointment`) |
| `POST /api/sessions` | Create session (returns `session_id`) |
| `POST /api/chat` | Multi-turn chat with LLM/tools |
| `POST /api/doctor/summary` | Doctor summary report |

## MCP Tools

| Tool | Description |
|------|-------------|
| `check_availability` | Query DB for available slots by doctor and date |
| `create_appointment` | Atomic booking + Google Calendar + email confirmation |
| `query_stats` | Stats between dates with optional symptom filter |
| `send_notification` | Slack webhook or in-app notification |

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_PROVIDER` | `demo` (default), `openai`, `anthropic`, `local` |
| `OPENAI_API_KEY` | For OpenAI |
| `ANTHROPIC_API_KEY` | For Claude |
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | Path to OAuth credentials (optional) |
| `GOOGLE_CALENDAR_ID` | Calendar ID (default: `primary`) |
| `SENDGRID_API_KEY` | For email (optional; demo mode if missing) |
| `SENDGRID_FROM_EMAIL` | Sender email |
| `SLACK_WEBHOOK_URL` | For notifications (optional; in-app if missing) |
| `BASE_URL` | Backend URL (default: http://localhost:8000) |

**Demo mode:** Without external credentials, Google Calendar, SendGrid, and Slack calls are stubbed. MCP tools remain fully functional; data is stored in the DB.

## Testing

```bash
cd backend
pytest tests/ -v
```

## Architecture Notes

- **MCP approach:** Custom registry (no `fastapi_mcp`); tools defined in `mcp_registry.py`, invoked at `POST /mcp/tools/{name}/call`.
- **Multi-turn:** Session + PromptHistory tables persist conversation; last N messages sent as context to the LLM.
- **Agent demo:** `scripts/run_agent_demo.py` discovers tools from `GET /mcp/tools`, sends a user message, and handles tool calls (OpenAI/Claude or demo mode).

## License

MIT
