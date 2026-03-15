"""MCP tool implementations used by the registry and chat flow."""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Appointment, Doctor, DoctorSlot, InAppNotification, Patient
from app.calendar_integration import add_event_to_calendar
from app.email_integration import send_confirmation


def _serialize_slot(slot: DoctorSlot) -> dict[str, Any]:
    return {
        "slot_id": slot.id,
        "doctor": slot.doctor.name if slot.doctor else None,
        "doctor_id": slot.doctor_id,
        "date": slot.date.strftime("%Y-%m-%d"),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
    }


def _serialize_appointment(appointment: Appointment) -> dict[str, Any]:
    return {
        "appointment_id": appointment.id,
        "doctor": appointment.doctor.name if appointment.doctor else None,
        "doctor_id": appointment.doctor_id,
        "patient": appointment.patient.name if appointment.patient else None,
        "patient_email": appointment.patient.email if appointment.patient else None,
        "date": appointment.appointment_date.strftime("%Y-%m-%d"),
        "start_time": appointment.start_time.strftime("%H:%M"),
        "end_time": appointment.slot.end_time.strftime("%H:%M") if appointment.slot else None,
        "slot_id": appointment.slot_id,
        "status": appointment.status,
        "calendar_event_id": appointment.calendar_event_id,
    }


def list_doctors(db: Session) -> dict[str, Any]:
    """Return all configured doctors with light scheduling metadata."""
    doctors_payload = []
    doctors = db.query(Doctor).order_by(Doctor.name.asc()).all()
    for doctor in doctors:
        next_slot = (
            db.query(DoctorSlot)
            .filter(
                DoctorSlot.doctor_id == doctor.id,
                DoctorSlot.is_available.is_(True),
                DoctorSlot.date >= datetime.utcnow().date(),
            )
            .order_by(DoctorSlot.date.asc(), DoctorSlot.start_time.asc())
            .first()
        )
        available_count = (
            db.query(DoctorSlot)
            .filter(
                DoctorSlot.doctor_id == doctor.id,
                DoctorSlot.is_available.is_(True),
                DoctorSlot.date >= datetime.utcnow().date(),
            )
            .count()
        )
        doctors_payload.append(
            {
                "doctor_id": doctor.id,
                "name": doctor.name,
                "specialization": doctor.specialization,
                "email": doctor.email,
                "available_slots": available_count,
                "next_available_slot": _serialize_slot(next_slot) if next_slot else None,
            }
        )
    return {"doctors": doctors_payload}


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
            available.append(_serialize_slot(slot))
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
        alternatives.append(_serialize_slot(slot))
        if len(alternatives) >= limit:
            break
    return alternatives


def _resolve_target_slot(
    db: Session,
    current_doctor_name: str,
    slot_id: Optional[int] = None,
    date_str: Optional[str] = None,
    start_time_str: Optional[str] = None,
    doctor_name: Optional[str] = None,
) -> tuple[Optional[Doctor], Optional[DoctorSlot], Optional[dict[str, Any]]]:
    doctor = None
    slot = None
    desired_doctor_name = doctor_name or current_doctor_name

    if slot_id is not None:
        slot = db.query(DoctorSlot).filter(DoctorSlot.id == slot_id).first()
        if not slot:
            return None, None, {
                "success": False,
                "error": f"Slot {slot_id} was not found.",
                "alternative_slots": find_next_available_slots(
                    db,
                    desired_doctor_name,
                    datetime.utcnow().strftime("%Y-%m-%d"),
                ),
            }
        doctor = db.query(Doctor).filter(Doctor.id == slot.doctor_id).first()
        return doctor, slot, None

    doctor = db.query(Doctor).filter(Doctor.name.ilike(f"%{desired_doctor_name}%")).first()
    if not doctor:
        return None, None, {"success": False, "error": f"Doctor '{desired_doctor_name}' not found."}

    if not (date_str and start_time_str):
        return doctor, None, {
            "success": False,
            "error": "Provide new_slot_id or date_str and start_time_str.",
        }

    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        start_t = datetime.strptime(start_time_str, "%H:%M").time()
    except ValueError:
        return doctor, None, {"success": False, "error": "Invalid date or time format."}

    slot = db.query(DoctorSlot).filter(
        DoctorSlot.doctor_id == doctor.id,
        DoctorSlot.date == appt_date,
        DoctorSlot.start_time == start_t,
    ).first()
    if not slot:
        return doctor, None, {
            "success": False,
            "error": "The requested slot does not exist.",
            "alternative_slots": find_next_available_slots(db, doctor.name, date_str),
        }

    return doctor, slot, None


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


def list_patient_appointments(
    db: Session,
    patient_email: str,
    include_cancelled: bool = False,
) -> dict[str, Any]:
    """Return a patient's appointments for self-service management."""
    if not patient_email:
        return {"appointments": [], "error": "Patient email is required."}

    patient = db.query(Patient).filter(Patient.email == patient_email).first()
    if not patient:
        return {"appointments": [], "patient_email": patient_email}

    appointments_query = db.query(Appointment).filter(Appointment.patient_id == patient.id)
    if not include_cancelled:
        appointments_query = appointments_query.filter(Appointment.status != "cancelled")

    appointments = (
        appointments_query
        .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        .all()
    )
    return {
        "patient": patient.name,
        "patient_email": patient.email,
        "appointments": [_serialize_appointment(appointment) for appointment in appointments],
    }


def cancel_appointment(
    db: Session,
    appointment_id: int,
    patient_email: str,
) -> dict[str, Any]:
    """Cancel a patient's appointment and release the reserved slot."""
    appointment = (
        db.query(Appointment)
        .join(Patient)
        .filter(Appointment.id == appointment_id, Patient.email == patient_email)
        .first()
    )
    if not appointment:
        return {"success": False, "error": "Appointment not found for this patient."}
    if appointment.status == "cancelled":
        return {"success": False, "error": "Appointment is already cancelled."}

    if appointment.slot:
        appointment.slot.is_available = True
    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)
    return {
        "success": True,
        "message": "Appointment cancelled successfully.",
        "appointment": _serialize_appointment(appointment),
    }


def reschedule_appointment(
    db: Session,
    appointment_id: int,
    patient_email: str,
    new_slot_id: Optional[int] = None,
    doctor_name: Optional[str] = None,
    date_str: Optional[str] = None,
    start_time_str: Optional[str] = None,
) -> dict[str, Any]:
    """Move an appointment to a new slot and release the old one."""
    appointment = (
        db.query(Appointment)
        .join(Patient)
        .filter(Appointment.id == appointment_id, Patient.email == patient_email)
        .first()
    )
    if not appointment:
        return {"success": False, "error": "Appointment not found for this patient."}
    if appointment.status == "cancelled":
        return {"success": False, "error": "Cancelled appointments cannot be changed."}

    target_doctor, target_slot, error = _resolve_target_slot(
        db,
        current_doctor_name=appointment.doctor.name,
        slot_id=new_slot_id,
        date_str=date_str,
        start_time_str=start_time_str,
        doctor_name=doctor_name,
    )
    if error:
        return error
    if not target_doctor or not target_slot:
        return {"success": False, "error": "Unable to resolve the new appointment slot."}
    if appointment.slot_id == target_slot.id:
        return {"success": False, "error": "Choose a different slot to reschedule."}

    existing = db.query(Appointment).filter(Appointment.slot_id == target_slot.id).first()
    if existing or not target_slot.is_available:
        return {
            "success": False,
            "error": "The selected new slot is already booked.",
            "alternative_slots": find_next_available_slots(
                db,
                target_doctor.name,
                target_slot.date.strftime("%Y-%m-%d"),
            ),
        }

    old_slot = appointment.slot
    try:
        if old_slot:
            old_slot.is_available = True
        target_slot.is_available = False
        appointment.doctor_id = target_doctor.id
        appointment.slot_id = target_slot.id
        appointment.appointment_date = target_slot.date
        appointment.start_time = target_slot.start_time
        appointment.status = "confirmed"
        appointment.calendar_event_id = add_event_to_calendar(
            doctor_name=target_doctor.name,
            patient_name=appointment.patient.name,
            patient_email=appointment.patient.email,
            start_datetime=datetime.combine(target_slot.date, target_slot.start_time),
            end_datetime=datetime.combine(target_slot.date, target_slot.end_time),
        )
        email_sent = send_confirmation(
            to_email=appointment.patient.email,
            patient_name=appointment.patient.name,
            doctor_name=target_doctor.name,
            appointment_date=target_slot.date.strftime("%Y-%m-%d"),
            start_time=target_slot.start_time.strftime("%H:%M"),
        )
        db.commit()
        db.refresh(appointment)
    except Exception as exc:
        db.rollback()
        return {"success": False, "error": f"Reschedule failed: {exc}"}

    return {
        "success": True,
        "message": "Appointment updated successfully.",
        "appointment": _serialize_appointment(appointment),
        "email_sent": email_sent,
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
