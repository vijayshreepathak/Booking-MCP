/**
 * Client wrapper for backend API.
 */

const API_BASE = import.meta.env.VITE_API_URL || "";

export async function createSession() {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("Failed to create session");
  const data = await res.json();
  return data.session_id;
}

export async function login(credentials) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(error.detail || "Login failed");
  }
  return res.json();
}

export async function getSessionHistory(sessionId) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/history`);
  if (!res.ok) throw new Error("Failed to load session history");
  return res.json();
}

export async function sendChat(sessionId, message, patientProfile = {}) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      patient_name: patientProfile.patientName || undefined,
      patient_email: patientProfile.patientEmail || undefined,
    }),
  });
  if (!res.ok) throw new Error("Chat request failed");
  return res.json();
}

export async function getDoctorSummary(doctorName, prompt) {
  const res = await fetch(`${API_BASE}/api/doctor/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_name: doctorName, prompt: prompt || undefined }),
  });
  if (!res.ok) throw new Error("Doctor summary failed");
  return res.json();
}
