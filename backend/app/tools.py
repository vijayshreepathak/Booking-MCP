"""MCP tool definitions: check_availability, create_appointment, query_stats, send_notification."""
import json
from datetime import datetime, date, time, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import Doctor, DoctorSlot, Patient, Appointment, InAppNotification
from app.calendar_integration import add_event_to_calendar
from app.email_integration import send_confirmation


def check_availability(
    db: Session,
    doctor_name: str,
    date_str: str,
) -> dict[str, Any]:
    """
    Query DB for available slots for a doctor on a given date.
    Returns available_slots array with slot_id, start_time, end_time.
    """
    try:
        slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"available_slots": [], "error": "Invalid date format. Use YYYY-MM-DD."}

    doctor = db.query(Doctor).filter(Doctor.name.ilike(f"%{doctor_name}%")).first()
    if not doctor:
        return {"available_slots": [], "error": f"Doctor '{doctor_name}' not found."}

    # Slots that have no linked appointment
    available = []
    for slot in db.query(DoctorSlot).filter(
        DoctorSlot.doctor_id == doctor.id,
        DoctorSlot.date == slot_date,
        DoctorSlot.is_available == True,
    ).all():
        has_appt = db.query(Appointment).filter(Appointment.slot_id == slot.id).first()
        if not has_appt:
            available.append({
                "slot_id": slot.id,
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
                "date": slot.date.strftime("%Y-%m-%d"),
            })
    return {"available_slots": available, "doctor": doctor.name}


def create_appointment(
    db: Session,
    doctor_name: str,
    patient_name: str,
    patient_email: str,
    slot_id: Optional[int] = None,
    date_str: Optional[str] = None,
    start_time_str: Optional[str] = None,
    symptom: str = "general",
) -> dict[str, Any]:
    """
    Atomic DB booking: find/create patient, book slot, call Google Calendar, send email.
    Either slot_id OR (date_str + start_time_str) must be provided.
    """
    doctor = db.query(Doctor).filter(Doctor.name.ilike(f"%{doctor_name}%")).first()
    if not doctor:
        return {"success": False, "error": f"Doctor '{doctor_name}' not found."}

    patient = db.query(Patient).filter(Patient.email == patient_email).first()
    if not patient:
        patient = Patient(name=patient_name, email=patient_email)
        db.add(patient)
        db.flush()

    slot = None
    if slot_id:
        slot = db.query(DoctorSlot).filter(
            DoctorSlot.id == slot_id,
            DoctorSlot.doctor_id == doctor.id,
            DoctorSlot.is_available == True,
        ).first()
        if not slot:
            existing = db.query(Appointment).filter(Appointment.slot_id == slot_id).first()
            if existing:
                return {"success": False, "error": "Slot is already booked."}
            slot = db.query(DoctorSlot).filter(DoctorSlot.id == slot_id).first()
            if not slot:
                return {"success": False, "error": f"Slot {slot_id} not found."}

    if not slot and date_str and start_time_str:
        try:
            appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_t = datetime.strptime(start_time_str, "%H:%M").time()
        except ValueError:
            return {"success": False, "error": "Invalid date or time format."}
        slot = db.query(DoctorSlot).filter(
            DoctorSlot.doctor_id == doctor.id,
            DoctorSlot.date == appt_date,
            DoctorSlot.start_time == start_t,
            DoctorSlot.is_available == True,
        ).first()
        if not slot:
            # Create ad-hoc slot for flexibility
            from datetime import time as dt_time
            end_t = (datetime.combine(date(1, 1, 1), start_t) + timedelta(minutes=30)).time()
            slot = DoctorSlot(
                doctor_id=doctor.id,
                date=appt_date,
                start_time=start_t,
                end_time=end_t,
                is_available=True,
            )
            db.add(slot)
            db.flush()

    if not slot:
        return {"success": False, "error": "Provide slot_id or date_str and start_time_str."}

    # Check not already booked
    existing = db.query(Appointment).filter(Appointment.slot_id == slot.id).first()
    if existing:
        return {"success": False, "error": "Slot is already booked."}

    start_dt = datetime.combine(slot.date, slot.start_time)
    end_dt = datetime.combine(slot.date, slot.end_time)
    calendar_event_id = add_event_to_calendar(
        doctor_name=doctor.name,
        patient_name=patient.name,
        patient_email=patient.email,
        start_datetime=start_dt,
        end_datetime=end_dt,
    )
    email_sent = send_confirmation(
        to_email=patient.email,
        patient_name=patient.name,
        doctor_name=doctor.name,
        appointment_date=slot.date.strftime("%Y-%m-%d"),
        start_time=slot.start_time.strftime("%H:%M"),
    )
    appointment = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        slot_id=slot.id,
        appointment_date=slot.date,
        start_time=slot.start_time,
        symptom=symptom,
        status="confirmed",
        calendar_event_id=calendar_event_id,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return {
        "success": True,
        "appointment_id": appointment.id,
        "doctor": doctor.name,
        "patient": patient.name,
        "date": slot.date.strftime("%Y-%m-%d"),
        "start_time": slot.start_time.strftime("%H:%M"),
        "calendar_event_id": calendar_event_id,
        "email_sent": email_sent,
    }


def query_stats(
    db: Session,
    doctor_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    symptom_filter: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return appointment stats between dates with optional doctor and symptom filters.
    """
    q = db.query(Appointment)
    if doctor_name:
        doc = db.query(Doctor).filter(Doctor.name.ilike(f"%{doctor_name}%")).first()
        if doc:
            q = q.filter(Appointment.doctor_id == doc.id)
    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d").date()
            q = q.filter(Appointment.appointment_date >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d").date()
            q = q.filter(Appointment.appointment_date <= ed)
        except ValueError:
            pass
    if symptom_filter:
        q = q.filter(Appointment.symptom.ilike(f"%{symptom_filter}%"))
    appointments = q.all()
    total = len(appointments)
    by_date = {}
    for a in appointments:
        k = a.appointment_date.strftime("%Y-%m-%d")
        by_date[k] = by_date.get(k, 0) + 1
    return {
        "total_appointments": total,
        "by_date": by_date,
        "symptom_filter": symptom_filter,
    }


def send_notification(
    db: Session,
    recipient: str,
    message: str,
    channel: str = "slack",
) -> dict[str, Any]:
    """
    Send notification via Slack webhook or create in-app notification record.
    """
    import os
    import httpx
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if webhook_url and not webhook_url.startswith("https://hooks.slack.com"):
        webhook_url = None  # placeholder
    if webhook_url:
        try:
            resp = httpx.post(
                webhook_url,
                json={"text": f"[To: {recipient}]\n{message}"},
                timeout=5,
            )
            if resp.status_code == 200:
                return {"success": True, "channel": "slack", "message": "Sent to Slack."}
        except Exception as e:
            pass  # fall through to in-app
    # Fallback: in-app notification
    notif = InAppNotification(recipient=recipient, message=message)
    db.add(notif)
    db.commit()
    return {"success": True, "channel": "in_app", "notification_id": notif.id}
