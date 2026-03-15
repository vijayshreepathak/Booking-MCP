import { useEffect, useMemo, useState } from "react";
import { getSessionHistory, sendChat } from "../api";

export default function Chat({ sessionId, sessionLabel }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [patientName, setPatientName] = useState(
    localStorage.getItem("appointment_patient_name") || "Vijayshree"
  );
  const [patientEmail, setPatientEmail] = useState(
    localStorage.getItem("appointment_patient_email") || "vijayshree@demo.local"
  );

  const quickPrompts = useMemo(
    () => [
      "Show Dr. Ahuja availability for tomorrow morning",
      "Book slot 10",
      "Book the 9:00 AM slot",
    ],
    []
  );

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

  const handleSend = async () => {
    if (!message.trim() || loading) return;
    const userMsg = message.trim();
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      localStorage.setItem("appointment_patient_name", patientName);
      localStorage.setItem("appointment_patient_email", patientEmail);
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
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error: " + err.message },
      ]);
    } finally {
      setLoading(false);
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
      </aside>

      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h2>Patient Assistant</h2>
            <p>Check availability, then book by slot number or time.</p>
          </div>
          <span className="session-pill">{sessionLabel || "Session active"}</span>
        </div>

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
                      onClick={() => setMessage(`Book slot ${slot.slot_id}`)}
                    >
                      <strong>Slot {slot.slot_id}</strong>
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
                        onClick={() => setMessage(`Book slot ${slot.slot_id}`)}
                      >
                        <strong>Slot {slot.slot_id}</strong>
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
                  <h3>Appointment confirmed</h3>
                  <div className="confirmation-grid">
                    <span>Doctor</span>
                    <strong>{m.appointment.doctor}</strong>
                    <span>Patient</span>
                    <strong>{m.appointment.patient}</strong>
                    <span>Date</span>
                    <strong>{m.appointment.date}</strong>
                    <span>Time</span>
                    <strong>
                      {m.appointment.start_time} - {m.appointment.end_time}
                    </strong>
                    <span>Email</span>
                    <strong>{m.appointment.patient_email}</strong>
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
