"""MCP tool implementations used by the registry and chat flow."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Appointment, Doctor, DoctorSlot, InAppNotification, Patient
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

    available = []
    for slot in db.query(DoctorSlot).filter(
        DoctorSlot.doctor_id == doctor.id,
        DoctorSlot.date == slot_date,
        DoctorSlot.is_available.is_(True),
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


def find_next_available_slots(
    db: Session,
    doctor_name: str,
    start_date: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return the next available slots for a doctor from a given date onward."""
    try:
        from_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        from_date = datetime.utcnow().date()

    doctor = db.query(Doctor).filter(Doctor.name.ilike(f"%{doctor_name}%")).first()
    if not doctor:
        return []

    slots = (
        db.query(DoctorSlot)
        .filter(
            DoctorSlot.doctor_id == doctor.id,
            DoctorSlot.date >= from_date,
            DoctorSlot.is_available.is_(True),
        )
        .order_by(DoctorSlot.date.asc(), DoctorSlot.start_time.asc())
        .all()
    )

    alternatives = []
    for slot in slots:
        has_appt = db.query(Appointment).filter(Appointment.slot_id == slot.id).first()
        if has_appt:
            continue
        alternatives.append(
            {
                "slot_id": slot.id,
                "date": slot.date.strftime("%Y-%m-%d"),
                "start_time": slot.start_time.strftime("%H:%M"),
                "end_time": slot.end_time.strftime("%H:%M"),
            }
        )
        if len(alternatives) >= limit:
            break
    return alternatives


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

    if not patient_email:
        return {"success": False, "error": "Patient email is required to confirm the booking."}

    patient = db.query(Patient).filter(Patient.email == patient_email).first()
    if not patient:
        patient = Patient(name=patient_name or "Guest Patient", email=patient_email)
        db.add(patient)
        db.flush()

    slot = None
    if slot_id is not None:
        slot = db.query(DoctorSlot).filter(
            DoctorSlot.id == slot_id,
            DoctorSlot.doctor_id == doctor.id,
        ).first()
        if not slot:
            return {
                "success": False,
                "error": f"Slot {slot_id} not found for {doctor.name}.",
                "alternative_slots": find_next_available_slots(
                    db,
                    doctor.name,
                    datetime.utcnow().strftime("%Y-%m-%d"),
                ),
            }
    elif date_str and start_time_str:
        try:
            appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_t = datetime.strptime(start_time_str, "%H:%M").time()
        except ValueError:
            return {"success": False, "error": "Invalid date or time format."}

        slot = db.query(DoctorSlot).filter(
            DoctorSlot.doctor_id == doctor.id,
            DoctorSlot.date == appt_date,
            DoctorSlot.start_time == start_t,
        ).first()
        if not slot:
            return {
                "success": False,
                "error": "The requested slot does not exist.",
                "alternative_slots": find_next_available_slots(db, doctor.name, date_str),
            }
    else:
        return {"success": False, "error": "Provide slot_id or date_str and start_time_str."}

    existing = db.query(Appointment).filter(Appointment.slot_id == slot.id).first()
    if existing or not slot.is_available:
        return {
            "success": False,
            "error": "Slot is already booked.",
            "alternative_slots": find_next_available_slots(
                db,
                doctor.name,
                slot.date.strftime("%Y-%m-%d"),
            ),
        }

    try:
        slot.is_available = False
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
    except Exception as exc:
        db.rollback()
        return {"success": False, "error": f"Booking failed: {exc}"}

    return {
        "success": True,
        "appointment_id": appointment.id,
        "doctor": doctor.name,
        "patient": patient.name,
        "patient_email": patient.email,
        "date": slot.date.strftime("%Y-%m-%d"),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "calendar_event_id": calendar_event_id,
        "email_sent": email_sent,
        "message": "Appointment booked successfully.",
        "alternative_slots": [],
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
    symptoms = {}
    for a in appointments:
        date_key = a.appointment_date.strftime("%Y-%m-%d")
        by_date[date_key] = by_date.get(date_key, 0) + 1
        symptom_key = a.symptom or "general"
        symptoms[symptom_key] = symptoms.get(symptom_key, 0) + 1
    return {
        "total_appointments": total,
        "by_date": by_date,
        "symptom_filter": symptom_filter,
        "symptoms": symptoms,
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
    if channel != "slack":
        webhook_url = None  # placeholder
    if webhook_url and not webhook_url.startswith("https://hooks.slack.com"):
        webhook_url = None
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
    return {
        "success": True,
        "channel": "in_app",
        "notification_id": notif.id,
        "recipient": recipient,
        "message": message,
    }
