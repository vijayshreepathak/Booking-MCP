import { useState } from "react";
import { sendChat } from "../api";

export default function Chat({ sessionId }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!message.trim() || loading) return;
    const userMsg = message.trim();
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    try {
      const res = await sendChat(sessionId, userMsg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.response, toolCalls: res.tool_calls },
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
    <div>
      <div
        style={{
          border: "1px solid #ccc",
          borderRadius: 8,
          minHeight: 300,
          padding: 16,
          marginBottom: 16,
          backgroundColor: "#fafafa",
        }}
      >
        {messages.length === 0 && (
          <p style={{ color: "#666" }}>
            Try: "I want to book an appointment with Dr. Ahuja tomorrow morning"
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 12,
              textAlign: m.role === "user" ? "right" : "left",
            }}
          >
            <span
              style={{
                display: "inline-block",
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: m.role === "user" ? "#0066cc" : "#e8e8e8",
                color: m.role === "user" ? "white" : "black",
              }}
            >
              {m.content}
            </span>
          </div>
        ))}
        {loading && <p style={{ color: "#666" }}>...</p>}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Type your message..."
          style={{ flex: 1, padding: 10 }}
        />
        <button onClick={handleSend} disabled={loading} style={{ padding: "10px 20px" }}>
          Send
        </button>
      </div>
    </div>
  );
}
