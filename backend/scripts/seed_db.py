#!/usr/bin/env python3
"""Seed the database with 2 doctors and sample slots."""
import os
import sys
from datetime import date, time, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import SessionLocal, init_db
from app.models import Doctor, DoctorSlot


def seed():
    init_db()
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Doctor).first():
            print("Database already seeded. Skipping.")
            return

        dr_ahuja = Doctor(name="Dr. Ahuja", specialization="General Physician", email="ahuja@clinic.com")
        dr_smith = Doctor(name="Dr. Smith", specialization="Cardiologist", email="smith@clinic.com")
        db.add(dr_ahuja)
        db.add(dr_smith)
        db.flush()

        today = date.today()
        for day_offset in range(7):
            d = today + timedelta(days=day_offset)
            for start_hour in [9, 10, 11, 14, 15, 16]:
                slot = DoctorSlot(
                    doctor_id=dr_ahuja.id,
                    date=d,
                    start_time=time(start_hour, 0),
                    end_time=time(start_hour, 30),
                    is_available=True,
                )
                db.add(slot)
            for start_hour in [9, 11, 15]:
                slot = DoctorSlot(
                    doctor_id=dr_smith.id,
                    date=d,
                    start_time=time(start_hour, 0),
                    end_time=time(start_hour, 30),
                    is_available=True,
                )
                db.add(slot)
        db.commit()
        print("Seeded 2 doctors (Dr. Ahuja, Dr. Smith) with sample slots.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
