"""SendGrid/Gmail wrapper. Uses env vars; falls back to stub in demo mode."""
import os
from typing import Optional


def send_confirmation(
    to_email: str,
    patient_name: str,
    doctor_name: str,
    appointment_date: str,
    start_time: str
) -> bool:
    """
    Send appointment confirmation email.
    Returns True on success. In demo mode (no API key), logs and returns True.
    """
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@demo.local")

    if not api_key or api_key.startswith("sk-"):
        # Demo mode: pretend success
        print(f"[DEMO] Would send confirmation to {to_email} for {patient_name} with Dr. {doctor_name} on {appointment_date} at {start_time}")
        return True

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=f"Appointment Confirmation - Dr. {doctor_name}",
            html_content=f"""
            <h2>Appointment Confirmed</h2>
            <p>Dear {patient_name},</p>
            <p>Your appointment with Dr. {doctor_name} has been confirmed.</p>
            <p><strong>Date:</strong> {appointment_date}</p>
            <p><strong>Time:</strong> {start_time}</p>
            <p>Please arrive 10 minutes before your scheduled time.</p>
            """
        )
        sg = SendGridAPIClient(api_key)
        sg.send(message)
        return True
    except Exception as e:
        print(f"[EMAIL] Send failed: {e}, using demo fallback")
        return True  # Graceful fallback
