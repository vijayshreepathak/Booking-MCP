import { useEffect, useMemo, useState } from "react";
import {
  deletePatientAppointment,
  getDoctors,
  getPatientAppointments,
  getSessionHistory,
  reschedulePatientAppointment,
  sendChat,
} from "../api";

export default function Chat({ sessionId, sessionLabel }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [appointmentsLoading, setAppointmentsLoading] = useState(false);
  const [selectedDoctor, setSelectedDoctor] = useState(
    localStorage.getItem("appointment_selected_doctor") || "Dr. Ahuja"
  );
  const [selectedDate, setSelectedDate] = useState(
    new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  );
  const [activeAppointmentId, setActiveAppointmentId] = useState(null);
  const [rescheduleTarget, setRescheduleTarget] = useState(null);
  const [patientName, setPatientName] = useState(
    localStorage.getItem("appointment_patient_name") || "Vijayshree"
  );
  const [patientEmail, setPatientEmail] = useState(
    localStorage.getItem("appointment_patient_email") || "vijayshree@demo.local"
  );

  const quickPrompts = useMemo(
    () => [
      `Show ${selectedDoctor} availability for tomorrow morning`,
      "Book slot 10",
      "Move appointment 1 to slot 10",
    ],
    [selectedDoctor]
  );

  async function loadAppointments(email) {
    if (!email) {
      setAppointments([]);
      return;
    }
    setAppointmentsLoading(true);
    try {
      const data = await getPatientAppointments(email);
      setAppointments(data.appointments || []);
    } catch {
      setAppointments([]);
    } finally {
      setAppointmentsLoading(false);
    }
  }

  useEffect(() => {
    let ignore = false;
    async function loadHistory() {
      try {
        const data = await getSessionHistory(sessionId);
        if (!ignore) {
          setMessages(
            (data.messages || []).map((item) => ({
              role: item.role,
              content: item.content,
              toolCalls: item.toolCalls || [],
              availableSlots: item.availableSlots || [],
              alternativeSlots: item.alternativeSlots || [],
              appointment: item.appointment || null,
            }))
          );
        }
      } catch {
        if (!ignore) {
          setMessages([]);
        }
      }
    }
    loadHistory();
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  useEffect(() => {
    let ignore = false;
    async function loadDoctors() {
      try {
        const data = await getDoctors();
        if (!ignore) {
          setDoctors(data.doctors || []);
          if (!localStorage.getItem("appointment_selected_doctor") && data.doctors?.[0]?.name) {
            setSelectedDoctor(data.doctors[0].name);
          }
        }
      } catch {
        if (!ignore) {
          setDoctors([]);
        }
      }
    }
    loadDoctors();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    loadAppointments(patientEmail);
  }, [patientEmail]);

  const addAssistantMessage = (content, appointment = null, alternativeSlots = []) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content,
        appointment,
        alternativeSlots,
      },
    ]);
  };

  const submitMessage = async (text) => {
    if (!text.trim() || loading) return;
    const userMsg = text.trim();
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      localStorage.setItem("appointment_patient_name", patientName);
      localStorage.setItem("appointment_patient_email", patientEmail);
      localStorage.setItem("appointment_selected_doctor", selectedDoctor);
      const res = await sendChat(sessionId, userMsg, { patientName, patientEmail });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          toolCalls: res.tool_calls,
          availableSlots: res.available_slots || [],
          alternativeSlots: res.alternative_slots || [],
          appointment: res.appointment || null,
        },
      ]);
      await loadAppointments(patientEmail);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error: " + err.message },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    await submitMessage(message);
  };

  const handleCheckAvailability = async () => {
    const prompt = `Show ${selectedDoctor} availability for ${selectedDate}`;
    await submitMessage(prompt);
  };

  const handleDeleteAppointment = async (appointmentId) => {
    if (!window.confirm("Delete this appointment?")) return;
    setActiveAppointmentId(appointmentId);
    try {
      const result = await deletePatientAppointment(appointmentId, patientEmail);
      addAssistantMessage(
        result.message || "Appointment deleted successfully.",
        result.appointment || null
      );
      setRescheduleTarget(null);
      await loadAppointments(patientEmail);
    } catch (error) {
      addAssistantMessage("Error: " + error.message);
    } finally {
      setActiveAppointmentId(null);
    }
  };

  const handlePickSlot = async (slot) => {
    if (!rescheduleTarget) {
      setMessage(`Book slot ${slot.slot_id}`);
      return;
    }

    setActiveAppointmentId(rescheduleTarget.appointment_id);
    try {
      const result = await reschedulePatientAppointment(rescheduleTarget.appointment_id, {
        patient_email: patientEmail,
        doctor_name: slot.doctor,
        new_slot_id: slot.slot_id,
      });
      addAssistantMessage(
        result.message || "Appointment updated successfully.",
        result.appointment || null,
        result.alternative_slots || []
      );
      setRescheduleTarget(null);
      await loadAppointments(patientEmail);
    } catch (error) {
      addAssistantMessage("Error: " + error.message);
    } finally {
      setActiveAppointmentId(null);
    }
  };

  return (
    <div className="layout-grid">
      <aside className="sidebar-card">
        <h3>Patient profile</h3>
        <label className="field-label">Patient name</label>
        <input
          className="text-input"
          value={patientName}
          onChange={(e) => setPatientName(e.target.value)}
          placeholder="Enter patient name"
        />

        <label className="field-label">Patient email</label>
        <input
          className="text-input"
          value={patientEmail}
          onChange={(e) => setPatientEmail(e.target.value)}
          placeholder="Enter patient email"
        />

        <label className="field-label">Choose doctor</label>
        <select
          className="text-input"
          value={selectedDoctor}
          onChange={(e) => {
            setSelectedDoctor(e.target.value);
            localStorage.setItem("appointment_selected_doctor", e.target.value);
          }}
        >
          {doctors.map((doctor) => (
            <option key={doctor.doctor_id} value={doctor.name}>
              {doctor.name} - {doctor.specialization}
            </option>
          ))}
        </select>

        <label className="field-label">Check date</label>
        <input
          type="date"
          className="text-input"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
        />

        <button type="button" className="primary-button secondary-button" onClick={handleCheckAvailability}>
          Show slots
        </button>

        <div className="helper-card">
          <strong>Doctors</strong>
          <div className="doctor-list">
            {doctors.map((doctor) => (
              <button
                key={doctor.doctor_id}
                type="button"
                className={doctor.name === selectedDoctor ? "doctor-card active" : "doctor-card"}
                onClick={() => {
                  setSelectedDoctor(doctor.name);
                  localStorage.setItem("appointment_selected_doctor", doctor.name);
                }}
              >
                <strong>{doctor.name}</strong>
                <span>{doctor.specialization}</span>
                <span>{doctor.available_slots} future slots</span>
              </button>
            ))}
          </div>
        </div>

        <div className="helper-card">
          <strong>Suggested prompts</strong>
          {quickPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="quick-prompt"
              onClick={() => setMessage(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="helper-card">
          <strong>Your appointments</strong>
          {appointmentsLoading && <p className="loading-copy">Loading appointments...</p>}
          {!appointmentsLoading && appointments.length === 0 && (
            <p className="loading-copy">No active appointments for this email.</p>
          )}
          {appointments.map((appointment) => (
            <div key={appointment.appointment_id} className="patient-appointment-card">
              <strong>
                #{appointment.appointment_id} {appointment.doctor}
              </strong>
              <span>
                {appointment.date} {appointment.start_time}
              </span>
              <span>Status: {appointment.status}</span>
              <div className="inline-actions">
                <button
                  type="button"
                  className={
                    rescheduleTarget?.appointment_id === appointment.appointment_id
                      ? "quick-prompt active-action"
                      : "quick-prompt"
                  }
                  onClick={() => {
                    setRescheduleTarget(appointment);
                    setSelectedDoctor(appointment.doctor);
                    addAssistantMessage(
                      `Reschedule mode enabled for appointment ${appointment.appointment_id}. Pick a doctor/date, click Show slots, then choose a new slot card.`
                    );
                  }}
                >
                  Change
                </button>
                <button
                  type="button"
                  className="quick-prompt danger-action"
                  disabled={activeAppointmentId === appointment.appointment_id}
                  onClick={() => handleDeleteAppointment(appointment.appointment_id)}
                >
                  {activeAppointmentId === appointment.appointment_id ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h2>Patient Assistant</h2>
            <p>Choose any doctor, book new slots, or change/delete your existing appointments.</p>
          </div>
          <span className="session-pill">{sessionLabel || "Session active"}</span>
        </div>

        {rescheduleTarget && (
          <div className="helper-card">
            <strong>Rescheduling appointment #{rescheduleTarget.appointment_id}</strong>
            <p className="loading-copy">
              Current booking: {rescheduleTarget.doctor} on {rescheduleTarget.date} at{" "}
              {rescheduleTarget.start_time}. Pick a new slot below or cancel reschedule mode.
            </p>
            <button
              type="button"
              className="quick-prompt"
              onClick={() => setRescheduleTarget(null)}
            >
              Cancel change mode
            </button>
          </div>
        )}

        <div className="chat-window">
          {messages.length === 0 && (
            <div className="empty-state">
              <p>Start with: "I want to book an appointment with Dr. Ahuja tomorrow morning"</p>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "message-row user" : "message-row assistant"}>
              <div className={m.role === "user" ? "message-bubble user" : "message-bubble assistant"}>
                {m.content}
              </div>

              {m.availableSlots?.length > 0 && (
                <div className="slots-grid">
                  {m.availableSlots.map((slot) => (
                    <button
                      key={slot.slot_id}
                      type="button"
                      className="slot-card"
                      onClick={() => handlePickSlot(slot)}
                    >
                      <strong>Slot {slot.slot_id}</strong>
                      <span>{slot.doctor}</span>
                      <span>{slot.date}</span>
                      <span>
                        {slot.start_time} - {slot.end_time}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {m.alternativeSlots?.length > 0 && (
                <div className="helper-card">
                  <strong>Recommended alternative slots</strong>
                  <div className="slots-grid" style={{ marginTop: 12 }}>
                    {m.alternativeSlots.map((slot) => (
                      <button
                        key={`alt-${slot.slot_id}`}
                        type="button"
                        className="slot-card"
                        onClick={() => handlePickSlot(slot)}
                      >
                        <strong>Slot {slot.slot_id}</strong>
                        <span>{slot.doctor}</span>
                        <span>{slot.date}</span>
                        <span>
                          {slot.start_time} - {slot.end_time}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {m.appointment && (
                <div className="confirmation-card">
                  <h3>
                    {m.appointment.status === "cancelled"
                      ? "Appointment cancelled"
                      : "Appointment details"}
                  </h3>
                  <div className="confirmation-grid">
                    <span>ID</span>
                    <strong>{m.appointment.appointment_id}</strong>
                    <span>Doctor</span>
                    <strong>{m.appointment.doctor}</strong>
                    <span>Patient</span>
                    <strong>{m.appointment.patient}</strong>
                    <span>Date</span>
                    <strong>{m.appointment.date}</strong>
                    <span>Time</span>
                    <strong>
                      {m.appointment.start_time}
                      {m.appointment.end_time ? ` - ${m.appointment.end_time}` : ""}
                    </strong>
                    <span>Email</span>
                    <strong>{m.appointment.patient_email}</strong>
                    <span>Status</span>
                    <strong>{m.appointment.status}</strong>
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && <p className="loading-copy">Assistant is checking tools...</p>}
        </div>

        <div className="composer">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type your message..."
            className="text-input composer-input"
          />
          <button onClick={handleSend} disabled={loading} className="primary-button">
            Send
          </button>
        </div>
      </section>
    </div>
  );
}
