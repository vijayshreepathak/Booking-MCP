"""Tests for the standalone MCP server protocol."""
import os
from datetime import date, time

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.db import Base, SessionLocal, engine
from app.mcp_server_app import app as mcp_app
from app.models import Doctor, DoctorSlot


def _seed_doctor_and_slot() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        doctor = Doctor(name="Dr. Ahuja", specialization="GP", email="ahuja@mcp.test")
        db.add(doctor)
        db.flush()
        db.add(
            DoctorSlot(
                doctor_id=doctor.id,
                date=date(2026, 3, 16),
                start_time=time(9, 0),
                end_time=time(9, 30),
                is_available=True,
            )
        )
        db.commit()
    finally:
        db.close()


def test_mcp_initialize_and_list_tools():
    _seed_doctor_and_slot()
    with TestClient(mcp_app) as client:
        initialize = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "pytest", "version": "1.0.0"},
                    "capabilities": {},
                },
            },
        )
        assert initialize.status_code == 200
        assert initialize.json()["result"]["capabilities"]["tools"] == {}

        tools = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list", "params": {}},
        )
        assert tools.status_code == 200
        names = [tool["name"] for tool in tools.json()["result"]["tools"]]
        assert "check_availability" in names
        assert "create_appointment" in names


def test_mcp_tools_call_returns_slot_data():
    _seed_doctor_and_slot()
    with TestClient(mcp_app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "check_availability",
                    "arguments": {
                        "doctor_name": "Dr. Ahuja",
                        "date_str": "2026-03-16",
                    },
                },
            },
        )
        assert response.status_code == 200
        structured = response.json()["result"]["structuredContent"]
        assert len(structured["available_slots"]) == 1
        assert structured["doctor"] == "Dr. Ahuja"
