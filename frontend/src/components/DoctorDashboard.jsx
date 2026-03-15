import { useState } from "react";
import { getDoctorSummary } from "../api";

export default function DoctorDashboard() {
  const [doctorName, setDoctorName] = useState("Dr. Ahuja");
  const [prompt, setPrompt] = useState("How many patients visited yesterday? Summarize today and tomorrow.");
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleGetSummary = async () => {
    setLoading(true);
    setReport(null);
    try {
      const data = await getDoctorSummary(doctorName, prompt);
      setReport(data);
    } catch (err) {
      setReport({ report: "Error: " + err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dashboard-shell">
      <section className="panel-card">
        <div className="panel-header">
          <div>
            <h2>Doctor Dashboard</h2>
            <p>Generate schedule summaries and verify doctor notifications.</p>
          </div>
        </div>

        <div className="dashboard-form">
          <div>
            <label className="field-label">Doctor name</label>
            <input
              type="text"
              value={doctorName}
              onChange={(e) => setDoctorName(e.target.value)}
              className="text-input"
            />
          </div>

          <div>
            <label className="field-label">Prompt</label>
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="text-input"
            />
          </div>

          <button onClick={handleGetSummary} disabled={loading} className="primary-button">
            {loading ? "Generating..." : "Get summary"}
          </button>
        </div>
      </section>

      {report && (
        <div className="dashboard-grid">
          <section className="panel-card">
            <h3>Daily metrics</h3>
            <div className="metric-grid">
              <div className="metric-card">
                <span>Today</span>
                <strong>{report.stats?.today ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>Yesterday</span>
                <strong>{report.stats?.yesterday ?? 0}</strong>
              </div>
              <div className="metric-card">
                <span>Tomorrow</span>
                <strong>{report.stats?.tomorrow ?? 0}</strong>
              </div>
            </div>
          </section>

          <section className="panel-card">
            <h3>Summary report</h3>
            <pre className="report-box">{report.report}</pre>
          </section>

          <section className="panel-card">
            <h3>Notification status</h3>
            <div className="notification-card">
              <span>Channel</span>
              <strong>{report.notification?.channel || "n/a"}</strong>
              <span>Recipient</span>
              <strong>{report.notification?.recipient || doctorName}</strong>
              <span>Status</span>
              <strong>{report.notification?.success ? "Delivered" : "Pending"}</strong>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
