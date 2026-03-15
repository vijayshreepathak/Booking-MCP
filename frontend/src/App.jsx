import { useState, useEffect } from "react";
import Chat from "./components/Chat";
import DoctorDashboard from "./components/DoctorDashboard";
import { createSession, login } from "./api";

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [sessionLabel, setSessionLabel] = useState("");
  const [tab, setTab] = useState("chat");
  const [auth, setAuth] = useState(null);
  const [loginForm, setLoginForm] = useState({
    role: "patient",
    email: "patient@demo.local",
    password: "patient123",
    name: "Demo Patient",
  });
  const [loginError, setLoginError] = useState("");

  useEffect(() => {
    const storedAuth = localStorage.getItem("appointment_auth");
    let sid = localStorage.getItem("appointment_session_id");
    if (storedAuth) {
      try {
        setAuth(JSON.parse(storedAuth));
      } catch {
        localStorage.removeItem("appointment_auth");
      }
    }
    if (!sid) {
      createSession()
        .then((id) => {
          localStorage.setItem("appointment_session_id", id);
          setSessionId(id);
          setSessionLabel("Active conversation");
        })
        .catch(() => {
          const fallback = "demo-session-" + Date.now();
          setSessionId(fallback);
          setSessionLabel("Active conversation");
        });
    } else {
      setSessionId(sid);
      setSessionLabel("Active conversation");
    }
  }, []);

  const handleLogin = async () => {
    try {
      setLoginError("");
      const data = await login(loginForm);
      setAuth(data);
      setSessionId(data.session_id);
      setSessionLabel(data.role === "doctor" ? "Doctor workspace" : "Active conversation");
      setTab(data.role === "doctor" ? "dashboard" : "chat");
      localStorage.setItem("appointment_session_id", data.session_id);
      localStorage.setItem("appointment_auth", JSON.stringify(data));
      if (data.role === "patient") {
        localStorage.setItem("appointment_patient_name", data.name);
        localStorage.setItem("appointment_patient_email", data.email);
      }
    } catch (error) {
      setLoginError(error.message);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("appointment_session_id");
    localStorage.removeItem("appointment_auth");
    setAuth(null);
    setSessionId(null);
    setSessionLabel("");
    createSession().then((id) => {
      localStorage.setItem("appointment_session_id", id);
      setSessionId(id);
      setSessionLabel("Active conversation");
    });
  };

  if (!auth) {
    return (
      <div className="page-shell">
        <div className="auth-card">
          <p className="eyebrow">Demo Login</p>
          <h1>Agentic Appointment MCP</h1>
          <p className="hero-copy">
            Sign in as a patient or doctor to test the assignment scenarios and bonus role-based access.
          </p>
          <div className="auth-grid">
            <div>
              <label className="field-label">Role</label>
              <select
                className="text-input"
                value={loginForm.role}
                onChange={(e) =>
                  setLoginForm((prev) => ({
                    ...prev,
                    role: e.target.value,
                    email: e.target.value === "doctor" ? "doctor@demo.local" : "patient@demo.local",
                    password: e.target.value === "doctor" ? "doctor123" : "patient123",
                    name: e.target.value === "doctor" ? "Dr. Ahuja" : "Demo Patient",
                  }))
                }
              >
                <option value="patient">Patient</option>
                <option value="doctor">Doctor</option>
              </select>
            </div>
            <div>
              <label className="field-label">Name</label>
              <input
                className="text-input"
                value={loginForm.name}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="field-label">Email</label>
              <input
                className="text-input"
                value={loginForm.email}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, email: e.target.value }))}
              />
            </div>
            <div>
              <label className="field-label">Password</label>
              <input
                type="password"
                className="text-input"
                value={loginForm.password}
                onChange={(e) => setLoginForm((prev) => ({ ...prev, password: e.target.value }))}
              />
            </div>
          </div>
          {loginError && <p className="error-copy">{loginError}</p>}
          <button className="primary-button" onClick={handleLogin}>
            Sign in
          </button>
          <div className="helper-card">
            <strong>Demo credentials</strong>
            <p>Patient: `patient@demo.local` / `patient123`</p>
            <p>Doctor: `doctor@demo.local` / `doctor123`</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Full-Stack Demo</p>
          <h1>Agentic Appointment MCP</h1>
          <p className="hero-copy">
            Book appointments through natural language and generate smart doctor summaries
            through MCP-discoverable backend tools.
          </p>
        </div>
        <div className="hero-badge">
          <span className="status-dot" />
          {auth.role === "doctor" ? "Doctor signed in" : "Patient signed in"}
        </div>
      </header>

      <nav className="tab-nav">
        <button
          className={tab === "chat" ? "tab-button active" : "tab-button"}
          onClick={() => setTab("chat")}
          disabled={auth.role === "doctor"}
        >
          Patient Assistant
        </button>
        <button
          className={tab === "dashboard" ? "tab-button active" : "tab-button"}
          onClick={() => setTab("dashboard")}
          disabled={auth.role === "patient"}
        >
          Doctor Dashboard
        </button>
        <button className="tab-button" onClick={handleLogout}>
          Logout
        </button>
      </nav>

      {tab === "chat" && sessionId && <Chat sessionId={sessionId} sessionLabel={sessionLabel} />}
      {tab === "dashboard" && <DoctorDashboard />}
    </div>
  );
}

export default App;
