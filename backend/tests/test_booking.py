"""
Unit tests for booking flow. Uses SQLite in-memory DB and mocks external APIs.
"""
import os
import pytest
from datetime import date, time
from unittest.mock import patch

# Use SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Doctor, DoctorSlot, Patient, Appointment
from app.tools import check_availability, create_appointment, query_stats


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
    db.add(dr)
    db.flush()
    slot = DoctorSlot(
        doctor_id=dr.id,
        date=date(2025, 3, 16),
        start_time=time(9, 0),
        end_time=time(9, 30),
        is_available=True,
    )
    db.add(slot)
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
