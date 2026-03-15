# Agentic Appointment MCP 🏥🤖

Welcome to the **Agentic Appointment MCP**! This is a production-style full-stack demo showcasing the power of **Agentic AI with MCP (Model Context Protocol)**. 

This application bridges the gap between natural language processing and complex backend operations, creating a seamless experience for both patients and healthcare providers.

### 🌟 What this app does:
- **For Patients:** Discover doctor availability and book, reschedule, or cancel appointments using natural language.
- **For Doctors:** Request smart schedule summaries and receive automated notifications.
- **For AI Agents:** Dynamically discover and execute backend capabilities through a real MCP client/server workflow.

🔗 **GitHub repository:** [vijayshreepathak/Booking-MCP](https://github.com/vijayshreepathak/Booking-MCP)

---

## 🚀 Future Scope & Industry Applications

While this demo is built for the healthcare sector, the underlying **Agentic AI + MCP architecture** is highly adaptable. This system can be customized for various industries:

- **💇‍♀️ Salons & Spas:** Book haircuts, massages, or beauty treatments.
- **🏋️‍♂️ Fitness Centers:** Schedule personal training sessions or fitness classes.
- **🚗 Auto Repair Shops:** Book vehicle service appointments or inspections.
- **🏢 Consulting & Legal:** Schedule advisory meetings or legal consultations.
- **🍽️ Restaurants:** Manage table reservations and private dining bookings.

The core concept—allowing an AI agent to understand intent, check availability, and execute bookings across integrated systems—is a universal solution for any service-based industry.

---

## 🤝 Let's Connect!

Feel free to reach out if you have questions, feedback, or just want to connect!

- **Portfolio:** [https://vijayshree.xyz/](https://vijayshree.xyz/)
- **LinkedIn:** [Vijayshree Vaibhav](https://www.linkedin.com/in/vijayshreevaibhav)

---

## Assignment Coverage

### Core requirements covered

- True MCP client-server separation between the web backend and the MCP tool server
- FastAPI backend with MCP registry and tool-call endpoints
- Dedicated MCP server exposing `initialize`, `tools/list`, and `tools/call`
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
    B[FastAPI App Backend]
    C[MCP Client Layer]
    S[Standalone MCP Server]
    A[LLM Agent Orchestrator]
    T1[list_doctors]
    T2[check_availability]
    T3[create_appointment]
    T4[query_stats]
    T5[send_notification]
    DB[(PostgreSQL)]
    GC[Google Calendar Wrapper]
    EM[Email Wrapper]
    NF[Slack / In-App Notification]

    U --> F
    F --> B
    B --> A
    A --> C
    B --> C
    C --> S
    S --> T1
    S --> T2
    S --> T3
    S --> T4
    S --> T5
    T1 --> DB
    T2 --> DB
    T3 --> DB
    T3 --> GC
    T3 --> EM
    T4 --> DB
    T5 --> NF
```

### MCP flow in this implementation

1. The React frontend talks to the FastAPI backend.
2. The FastAPI backend acts as an **MCP client**, not as the tool executor.
3. A separate `mcp-server` process exposes tools over a JSON-RPC MCP interface at `POST /mcp`.
4. The backend discovers tools dynamically through `tools/list` and invokes them through `tools/call`.
5. The MCP server is the only layer that directly executes tool logic against the database and integrations.

## Project Structure

```text
backend/
  app/
    main.py
    mcp_client.py
    mcp_server_app.py
    tools.py
    tool_dispatcher.py
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
   - discovers tools from the MCP server
   - calls `check_availability` through the MCP client
   - returns available slots in chat and as clickable cards
4. Patient follows up with:
   - `Book slot 10`
   - or `Book the 9:00 AM slot`
5. Agent logic:
   - calls `create_appointment` through the MCP server
   - the MCP server writes the appointment to DB
   - the MCP server creates a Google Calendar event through the wrapper
   - the MCP server sends email through the wrapper
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
4. Backend invokes `query_stats` and `send_notification` through the MCP client/server boundary
5. If Slack is not configured, the report is stored as an in-app notification

## MCP Interface

### Protocol endpoint

- `POST /mcp` on the standalone MCP server

Supported MCP methods:

- `initialize`
- `tools/list`
- `tools/call`

### REST compatibility registry

- `GET /mcp/tools`

The FastAPI backend also exposes compatibility endpoints for easier manual testing and assignment checks. These endpoints proxy through the MCP server rather than executing tools directly.

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
| `POST /mcp` | Standalone MCP server protocol endpoint |
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
- MCP server: [http://localhost:8100/health](http://localhost:8100/health)
- Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)

The backend and MCP server both use the same database, and the backend talks to the MCP server through `MCP_SERVER_URL`.

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

#### 3. Run MCP server

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_db.py
uvicorn app.mcp_server_app:app --reload --host 0.0.0.0 --port 8100
```

#### 4. Run backend

```bash
cd backend
pip install -r requirements.txt
python scripts/seed_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 5. Run frontend

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

- initializes an MCP session
- discovers tools through the MCP server
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
| `MCP_SERVER_URL` | MCP server endpoint used by the backend client |
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

- MCP protocol initialization
- MCP `tools/list` dynamic discovery
- MCP `tools/call` execution
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

- actual protocol-based MCP tool orchestration
- clear service boundary between backend client and MCP server
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
