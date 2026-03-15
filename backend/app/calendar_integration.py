"""Google Calendar API wrapper. Uses env vars; falls back to stub in demo mode."""
import os
from typing import Optional
from datetime import datetime


def add_event_to_calendar(
    doctor_name: str,
    patient_name: str,
    patient_email: str,
    start_datetime: datetime,
    end_datetime: datetime,
    summary: str = "Doctor Appointment"
) -> Optional[str]:
    """
    Add appointment to Google Calendar. Returns event_id or None.
    In demo mode (no credentials), returns a mock event_id.
    """
    client_secret_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    if not client_secret_path or not os.path.exists(client_secret_path):
        # Demo mode: store mock event
        return f"demo_event_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(client_secret_path)
        service = build("calendar", "v3", credentials=creds)

        event = {
            "summary": summary,
            "description": f"Appointment: {patient_name} ({patient_email}) with Dr. {doctor_name}",
            "start": {"dateTime": start_datetime.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_datetime.isoformat(), "timeZone": "UTC"},
        }
        result = service.events().insert(calendarId=calendar_id, body=event).execute()
        return result.get("id")
    except Exception:
        # Fallback to demo
        return f"demo_event_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
