"""SQLAlchemy models for the appointment system."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Date, Time
from sqlalchemy.orm import relationship

from app.db import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    specialization = Column(String(100))
    email = Column(String(255), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    slots = relationship("DoctorSlot", back_populates="doctor")
    appointments = relationship("Appointment", back_populates="doctor")


class DoctorSlot(Base):
    __tablename__ = "doctor_slots"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="slots")
    appointment = relationship("Appointment", back_populates="slot", uselist=False)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    appointments = relationship("Appointment", back_populates="patient")


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("doctor_slots.id"), nullable=True)
    appointment_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    symptom = Column(String(255), default="general")
    status = Column(String(50), default="confirmed")
    calendar_event_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    slot = relationship("DoctorSlot", back_populates="appointment")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    role = Column(String(50), default="patient")  # patient or doctor
    created_at = Column(DateTime, default=datetime.utcnow)
    history = relationship("PromptHistory", back_populates="session", order_by="PromptHistory.created_at")


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user or assistant
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)  # JSON string of tool invocations
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="history")


class InAppNotification(Base):
    """Fallback when Slack webhook is not configured."""
    __tablename__ = "in_app_notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read = Column(Boolean, default=False)
