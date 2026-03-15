import { useState, useEffect } from "react";
import Chat from "./components/Chat";
import DoctorDashboard from "./components/DoctorDashboard";
import { createSession } from "./api";

function App() {
  const [sessionId, setSessionId] = useState(null);
  const [tab, setTab] = useState("chat");

  useEffect(() => {
    let sid = localStorage.getItem("appointment_session_id");
    if (!sid) {
      createSession()
        .then((id) => {
          localStorage.setItem("appointment_session_id", id);
          setSessionId(id);
        })
        .catch(() => {
          setSessionId("demo-session-" + Date.now());
        });
    } else {
      setSessionId(sid);
    }
  }, []);

  return (
    <div style={{ fontFamily: "system-ui", maxWidth: 900, margin: "0 auto", padding: 20 }}>
      <h1>Agentic Appointment MCP</h1>
      <nav style={{ marginBottom: 20 }}>
        <button
          onClick={() => setTab("chat")}
          style={{ marginRight: 10, padding: "8px 16px", cursor: "pointer" }}
        >
          Patient Chat
        </button>
        <button
          onClick={() => setTab("dashboard")}
          style={{ padding: "8px 16px", cursor: "pointer" }}
        >
          Doctor Dashboard
        </button>
      </nav>
      {tab === "chat" && sessionId && <Chat sessionId={sessionId} />}
      {tab === "dashboard" && <DoctorDashboard />}
    </div>
  );
}

export default App;
