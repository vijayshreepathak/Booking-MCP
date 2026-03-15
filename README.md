# Agentic Appointment MCP

Production-style full-stack demo for the **Full-Stack Developer Intern Assignment – Agentic AI with MCP**. The app lets:

- patients discover doctor availability and book appointments through natural language
- doctors request smart schedule summaries and receive notifications
- an LLM agent discover backend capabilities dynamically through an MCP-style tool registry

GitHub repository: [vijayshreepathak/Booking-MCP](https://github.com/vijayshreepathak/Booking-MCP)

## Assignment Coverage

### Core requirements covered

- FastAPI backend with MCP registry and tool-call endpoints
- React frontend for patient chat and doctor dashboard
- PostgreSQL-backed scheduling and appointment data
- Multi-turn continuity using `Session` and `PromptHistory`
- Tool discovery via `GET /mcp/tools`
- Tool invocation via `POST /mcp/tools/{tool_name}/call`
- Booking flow with calendar + email integration wrappers
- Doctor reporting flow with alternate notification channel
- Dockerized local run with seeded data
- Automated tests for booking flow

### Bonus features covered

- Simple role-based login: patient vs doctor
- Multiple doctor selection in the patient flow
- Patient self-service appointment change and delete actions
- Prompt history tracking and restore on refresh
- Auto-rescheduling suggestions when a requested slot is unavailable

## Architecture

```mermaid
flowchart LR
    U[User]
    F[React Frontend]
    B[FastAPI Backend]
    M[MCP Registry]
    A[Agent Orchestrator]
    T1[check_availability]
    T2[create_appointment]
    T3[query_stats]
    T4[send_notification]
    DB[(PostgreSQL)]
    GC[Google Calendar Wrapper]
    EM[Email Wrapper]
    NF[Slack / In-App Notification]

    U --> F
    F --> B
    B --> M
    B --> A
    A --> T1
    A --> T2
    A --> T3
    A --> T4
    T1 --> DB
    T2 --> DB
    T2 --> GC
    T2 --> EM
    T3 --> DB
    T4 --> NF
```

## Project Structure

```text
backend/
  app/
    main.py
    tools.py
    models.py
    db.py
    calendar_integration.py
    email_integration.py
    mcp_registry.py
    llm_orchestrator.py
  alembic/
  scripts/
    seed_db.py
    run_agent_demo.py
  tests/
frontend/
  src/
    App.jsx
    api.js
    components/
      Chat.jsx
      DoctorDashboard.jsx
docker-compose.yml
.env.example
README.md
```

## How It Works

### Scenario 1: Patient appointment scheduling

1. Patient signs in with the patient demo account.
2. Patient can select from multiple doctors in the sidebar or ask in chat: `I want to book an appointment with Dr. Ahuja tomorrow morning`
3. Agent logic:
   - interprets the request
   - calls `check_availability`
   - returns available slots in chat and as clickable cards
4. Patient follows up with:
   - `Book slot 10`
   - or `Book the 9:00 AM slot`
5. Agent logic:
   - calls `create_appointment`
   - writes appointment to DB
   - creates a Google Calendar event through the wrapper
   - sends email through the wrapper
   - returns a confirmation card in the UI
6. Patients can review current bookings, change to a different doctor/slot, or delete an appointment directly from the sidebar.
7. If the slot is unavailable, the backend returns alternative slots and the UI presents them as rescheduling options.

### Scenario 2: Doctor summary report

1. Doctor signs in with the doctor demo account.
2. Doctor opens the dashboard or enters a prompt like:
   - `How many patients visited yesterday?`
   - `How many appointments do I have today, tomorrow`
   - `How many patient with fever`
3. Backend calls `query_stats`
4. Backend formats a readable report and sends it through `send_notification`
5. If Slack is not configured, the report is stored as an in-app notification

## MCP Interface

### Tool registry

- `GET /mcp/tools`

Returns metadata for every tool:

- tool name
- description
- input schema
- output schema
- call URL

### Tool call endpoint

- `POST /mcp/tools/{tool_name}/call`

Supported tools:

| Tool | Purpose |
|---|---|
| `list_doctors` | Return available doctors with specialization and next slot |
| `check_availability` | Return available slots for a doctor/date |
| `create_appointment` | Book appointment atomically and trigger integrations |
| `query_stats` | Return doctor stats between dates with optional symptom filter |
| `send_notification` | Send Slack webhook or store in-app notification |
| `list_patient_appointments` | Return current patient bookings |
| `cancel_appointment` | Cancel a patient booking and free the slot |
| `reschedule_appointment` | Move a booking to another doctor/slot |

## API Overview

| Endpoint | Description |
|---|---|
| `POST /api/auth/login` | Demo role-based login for patient or doctor |
| `GET /api/doctors` | List doctors for UI selection |
| `POST /api/sessions` | Create a session |
| `GET /api/sessions/{session_id}/history` | Load full conversation history |
| `GET /api/patient/appointments` | List patient appointments by email |
| `DELETE /api/patient/appointments/{appointment_id}` | Cancel/delete a patient appointment |
| `POST /api/patient/appointments/{appointment_id}/reschedule` | Change a patient appointment |
| `POST /api/chat` | Multi-turn patient chat endpoint |
| `POST /api/doctor/summary` | Doctor dashboard summary endpoint |
| `GET /mcp/tools` | MCP registry metadata |
| `POST /mcp/tools/{tool_name}/call` | Tool execution endpoint |
| `GET /health` | Health check |

## Demo Credentials

### Patient

- email: `patient@demo.local`
- password: `patient123`

### Doctor

- email: `doctor@demo.local`
- password: `doctor123`

You can override these through `.env`.

## Running the Project

### Docker run

```bash
docker-compose up --build
```

Available URLs:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend: [http://localhost:8000](http://localhost:8000)
- Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

The backend seeds 2 doctors and sample slots automatically.

### Local run

#### 1. Configure environment

```bash
cp .env.example .env
```

#### 2. Start PostgreSQL

Create a DB named `appointment_db`, then export:

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/appointment_db
```

#### 3. Run backend

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. Run frontend

```bash
cd frontend
npm install
npm run dev
```

## Agent Demo Script

Run:

```bash
cd backend
python scripts/run_agent_demo.py
```

The script:

- fetches `GET /mcp/tools`
- builds a system prompt
- sends the example booking request
- handles tool calls
- prints final output

## Configuration

Copy `.env.example` to `.env`.

### Always useful

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Database connection string |
| `BASE_URL` | Backend URL used in MCP call metadata |
| `LLM_PROVIDER` | `demo`, `openai`, `anthropic`, or `local` |

### Demo login

| Variable | Purpose |
|---|---|
| `DEMO_PATIENT_EMAIL` | Demo patient login |
| `DEMO_PATIENT_PASSWORD` | Demo patient password |
| `DEMO_PATIENT_NAME` | Demo patient display name |
| `DEMO_DOCTOR_EMAIL` | Demo doctor login |
| `DEMO_DOCTOR_PASSWORD` | Demo doctor password |
| `DEMO_DOCTOR_NAME` | Demo doctor display name |

### Hosted or local LLM

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI tool-calling |
| `OPENAI_MODEL` | OpenAI model |
| `ANTHROPIC_API_KEY` | Claude tool-calling |
| `ANTHROPIC_MODEL` | Claude model |
| `LOCAL_LLM_URL` | OpenAI-compatible local endpoint |
| `LOCAL_MODEL` | Local model name |

### External integrations

| Variable | Purpose |
|---|---|
| `GOOGLE_CALENDAR_CREDENTIALS_PATH` | Google auth credentials |
| `GOOGLE_CALENDAR_ID` | Calendar ID |
| `SENDGRID_API_KEY` | Email service key |
| `SENDGRID_FROM_EMAIL` | Outbound email address |
| `SLACK_WEBHOOK_URL` | Slack notifications |

### What requires your API keys

- No keys are required for the full demo flow
- Real Google Calendar events require Google credentials
- Real emails require SendGrid
- Real Slack notifications require a Slack webhook
- Real hosted LLM tool-calling requires OpenAI or Anthropic credentials

Without those keys, the app gracefully falls back to demo mode and still completes the assignment flow.

## Screenshots

### Login Page

![Login Page](backend/Screenshots/LoginPage.png)

### Patient Booking Flow

![Patient Booking Flow](backend/Screenshots/Patient1.png)

### Patient Dashboard With Change/Delete

![Patient Dashboard With Change Delete](backend/Screenshots/PatientDashbard2.png)

### Doctor Dashboard

![Doctor Dashboard](backend/Screenshots/DoctorDashboard.png)

## Sample Test Prompts

### Patient flow

- `I want to book an appointment with Dr. Ahuja tomorrow morning`
- `Show Dr. Smith availability for tomorrow morning`
- `Check Dr. Ahuja availability for Friday afternoon`
- `Please book the 3 PM slot`
- `Book slot 10`
- `Move appointment 1 to slot 10`
- `Cancel appointment 1`

### Doctor flow

- `How many patients visited yesterday?`
- `How many appointments do I have today, tomorrow`
- `How many patient with fever`

## Testing and Verification

### Backend tests

```bash
cd backend
pytest tests/ -v
```

### Frontend build

```bash
cd frontend
npm run build
```

### What is verified

- multiple doctor listing and selection
- booking success
- patient appointment change and delete flows
- double-booking prevention
- alternative slot suggestions
- stats query
- demo login endpoint
- Dockerized frontend/backend startup
- patient multi-turn history restore

## Notes on Production Readiness

This submission is still a demo, but it includes several production-style practices:

- modular backend structure
- clear MCP tool boundaries
- graceful fallback integrations
- structured API responses
- session and prompt history persistence
- Dockerized deployment
- automated tests

For a true production rollout, the next steps would be:

- JWT/session auth with hashed passwords
- proper migrations in deployment pipeline
- audit logging
- secrets management
- background job queue for email/calendar/notification retries
- observability and error reporting

## GitHub Push

Target repository: [vijayshreepathak/Booking-MCP](https://github.com/vijayshreepathak/Booking-MCP)

```bash
git remote add origin https://github.com/vijayshreepathak/Booking-MCP.git
git branch -M main
git push -u origin main
```

## License

MIT
