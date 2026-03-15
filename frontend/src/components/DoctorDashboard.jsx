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
    <div>
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: 4 }}>Doctor Name</label>
        <input
          type="text"
          value={doctorName}
          onChange={(e) => setDoctorName(e.target.value)}
          style={{ padding: 8, width: 200 }}
        />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", marginBottom: 4 }}>Prompt (optional)</label>
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          style={{ padding: 8, width: "100%", maxWidth: 400 }}
        />
      </div>
      <button
        onClick={handleGetSummary}
        disabled={loading}
        style={{ padding: "10px 20px", marginBottom: 16 }}
      >
        Get summary
      </button>
      {loading && <p>Loading...</p>}
      {report && (
        <div
          style={{
            border: "1px solid #ccc",
            borderRadius: 8,
            padding: 16,
            backgroundColor: "#f9f9f9",
          }}
        >
          <h3>Report for {report.doctor_name}</h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{report.report}</pre>
          {report.stats && (
            <div style={{ marginTop: 12, fontSize: 14 }}>
              Stats: Today {report.stats.today}, Yesterday {report.stats.yesterday}, Tomorrow{" "}
              {report.stats.tomorrow}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
