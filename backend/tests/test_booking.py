"""
Unit tests for booking flow. Uses SQLite in-memory DB and mocks external APIs.
"""
import os
import pytest
from datetime import date, time
from unittest.mock import patch
from fastapi.testclient import TestClient

# Use SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Doctor, DoctorSlot, Patient, Appointment
from app.tools import (
    cancel_appointment,
    check_availability,
    create_appointment,
    list_doctors,
    list_patient_appointments,
    query_stats,
    reschedule_appointment,
)
from app.main import app


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def seeded_db(db):
    dr = Doctor(name="Dr. Ahuja", specialization="GP", email="ahuja@test.com")
    dr2 = Doctor(name="Dr. Smith", specialization="Cardiology", email="smith@test.com")
    db.add(dr)
    db.add(dr2)
    db.flush()
    slot = DoctorSlot(
        doctor_id=dr.id,
        date=date(2025, 3, 16),
        start_time=time(9, 0),
        end_time=time(9, 30),
        is_available=True,
    )
    db.add(slot)
    db.add(
        DoctorSlot(
            doctor_id=dr.id,
            date=date(2025, 3, 16),
            start_time=time(10, 0),
            end_time=time(10, 30),
            is_available=True,
        )
    )
    db.add(
        DoctorSlot(
            doctor_id=dr2.id,
            date=date(2025, 3, 16),
            start_time=time(11, 0),
            end_time=time(11, 30),
            is_available=True,
        )
    )
    db.commit()
    db.refresh(slot)
    yield db


@patch("app.tools.add_event_to_calendar")
@patch("app.tools.send_confirmation")
def test_check_availability_returns_slots(mock_email, mock_calendar, seeded_db):
    result = check_availability(seeded_db, "Dr. Ahuja", "2025-03-16")
    assert "available_slots" in result
    assert len(result["available_slots"]) >= 1
    assert result["doctor"] == "Dr. Ahuja"


@patch("app.tools.add_event_to_calendar", return_value="demo_event_123")
@patch("app.tools.send_confirmation", return_value=True)
def test_create_appointment_success(mock_email, mock_calendar, seeded_db):
    slots = check_availability(seeded_db, "Dr. Ahuja", "2025-03-16")
    slot_id = slots["available_slots"][0]["slot_id"]

    result = create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Test Patient",
        patient_email="test@example.com",
        slot_id=slot_id,
    )
    assert result["success"] is True
    assert "appointment_id" in result
    assert result["doctor"] == "Dr. Ahuja"


@patch("app.tools.add_event_to_calendar", return_value="demo_event_123")
@patch("app.tools.send_confirmation", return_value=True)
def test_create_appointment_double_booking_fails(mock_email, mock_calendar, seeded_db):
    slots = check_availability(seeded_db, "Dr. Ahuja", "2025-03-16")
    slot_id = slots["available_slots"][0]["slot_id"]

    create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Patient 1",
        patient_email="p1@example.com",
        slot_id=slot_id,
    )
    result = create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Patient 2",
        patient_email="p2@example.com",
        slot_id=slot_id,
    )
    assert result["success"] is False
    assert "error" in result


def test_query_stats(seeded_db):
    result = query_stats(
        seeded_db,
        doctor_name="Dr. Ahuja",
        start_date="2025-03-01",
        end_date="2025-03-31",
    )
    assert "total_appointments" in result
    assert "by_date" in result


def test_list_doctors_returns_multiple_doctors(seeded_db):
    result = list_doctors(seeded_db)
    assert len(result["doctors"]) >= 2
    assert any(item["name"] == "Dr. Smith" for item in result["doctors"])


@patch("app.tools.add_event_to_calendar", return_value="demo_event_123")
@patch("app.tools.send_confirmation", return_value=True)
def test_create_appointment_returns_alternatives_when_booked(mock_email, mock_calendar, seeded_db):
    slots = check_availability(seeded_db, "Dr. Ahuja", "2025-03-16")
    slot_id = slots["available_slots"][0]["slot_id"]

    create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Patient 1",
        patient_email="p1@example.com",
        slot_id=slot_id,
    )
    result = create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Patient 2",
        patient_email="p2@example.com",
        slot_id=slot_id,
    )

    assert result["success"] is False
    assert "alternative_slots" in result


@patch("app.tools.add_event_to_calendar", return_value="demo_event_123")
@patch("app.tools.send_confirmation", return_value=True)
def test_patient_can_cancel_appointment(mock_email, mock_calendar, seeded_db):
    booking = create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Test Patient",
        patient_email="test@example.com",
        slot_id=1,
    )
    result = cancel_appointment(seeded_db, booking["appointment_id"], "test@example.com")
    assert result["success"] is True
    assert result["appointment"]["status"] == "cancelled"


@patch("app.tools.add_event_to_calendar", return_value="demo_event_456")
@patch("app.tools.send_confirmation", return_value=True)
def test_patient_can_reschedule_appointment(mock_email, mock_calendar, seeded_db):
    booking = create_appointment(
        seeded_db,
        doctor_name="Dr. Ahuja",
        patient_name="Test Patient",
        patient_email="test@example.com",
        slot_id=1,
    )
    appointments_before = list_patient_appointments(seeded_db, "test@example.com")
    assert len(appointments_before["appointments"]) == 1

    result = reschedule_appointment(
        seeded_db,
        booking["appointment_id"],
        "test@example.com",
        new_slot_id=3,
    )
    assert result["success"] is True
    assert result["appointment"]["doctor"] == "Dr. Smith"
    assert result["appointment"]["slot_id"] == 3


def test_demo_login_endpoint():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "role": "patient",
                "email": "patient@demo.local",
                "password": "patient123",
                "name": "Demo Patient",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "patient"
        assert data["email"] == "patient@demo.local"
