import { useState } from "react";

const API =
  import.meta.env.VITE_API_URL ||
  "https://ai-agent-lvvc.onrender.com";

export default function App() {
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  // TEMP USER (replace with Supabase Auth later)
  const [userId] = useState(() => {
    let id = localStorage.getItem("user_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("user_id", id);
    }
    return id;
  });

  // ROLE (DEV MODE – replace with real auth later)
  const [role, setRole] = useState(() => {
    return localStorage.getItem("role") || "resident";
  });

  const toggleRole = () => {
    const newRole = role === "admin" ? "resident" : "admin";
    setRole(newRole);
    localStorage.setItem("role", newRole);
  };

  // ----------------------------
  // BORRETTSLAG UX QUERIES
  // ----------------------------
  const quickQuestions = [
    "Når er det ro i bygget?",
    "Kan jeg ha husdyr i leiligheten?",
    "Hva gjelder ved oppussing?",
    "Hvor kaster jeg restavfall?",
    "Hvem kontakter jeg ved skade eller feil?",
  ];

  // ----------------------------
  // UPLOAD PDF (ADMIN ONLY)
  // ----------------------------
  const uploadPDF = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API}/upload`, {
        method: "POST",
        headers: {
          "user_id": userId,
        },
        body: formData,
      });

      if (!res.ok) throw new Error("Upload failed");

      setFile(null);
      alert("Dokument lastet opp ✔");
    } catch (err) {
      console.error(err);
      alert("Upload failed");
    }
  };

  // ----------------------------
  // CHAT
  // ----------------------------
  const askQuestion = async (overrideQuestion = null) => {
    const q = overrideQuestion || question;
    if (!q) return;

    setMessages((p) => [...p, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: q,
          user_id: userId,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();

      setMessages((p) => [
        ...p,
        {
          role: "bot",
          text: data.answer || "Ingen respons",
        },
      ]);
    } catch (err) {
      console.error(err);
      setMessages((p) => [
        ...p,
        {
          role: "bot",
          text: "Kunne ikke kontakte server",
        },
      ]);
    }

    setLoading(false);
    setQuestion("");
  };

  return (
    <div style={styles.bg}>
      <div style={styles.shell}>

        {/* SIDEBAR */}
        <div style={styles.sidebar}>
          <div style={styles.logo}>🏢 Borettslagsassistent</div>

          {/* DEV ROLE SWITCH */}
          <button onClick={toggleRole} style={styles.roleSwitch}>
            Bytt rolle (DEV): {role}
          </button>

          <div style={styles.role}>
            Aktiv rolle:{" "}
            <b>{role === "admin" ? "Styret (admin)" : "Beboer"}</b>
          </div>

          {/* ADMIN PANEL */}
          {role === "admin" && (
            <div style={styles.card}>
              <div style={styles.label}>Styret – dokumenthåndtering</div>

              <input
                type="file"
                onChange={(e) => setFile(e.target.files?.[0])}
              />

              <button
                onClick={uploadPDF}
                disabled={!file}
                style={{
                  ...styles.button,
                  opacity: !file ? 0.5 : 1,
                  cursor: !file ? "not-allowed" : "pointer",
                }}
              >
                Last opp PDF
              </button>
            </div>
          )}

          {/* QUICK ACTIONS */}
          <div style={styles.card}>
            <div style={styles.label}>Vanlige spørsmål</div>

            {quickQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => askQuestion(q)}
                style={styles.exampleBtn}
              >
                {q}
              </button>
            ))}
          </div>

          <div style={styles.card}>
            <div style={styles.label}>Bruker-ID</div>
            <div style={styles.smallText}>{userId}</div>
          </div>
        </div>

        {/* MAIN */}
        <div style={styles.main}>
          <div style={styles.topbar}>
            Søk i husordensregler og borettslagsdokumenter
          </div>

          <div style={styles.chat}>
            {messages.length === 0 && (
              <div style={styles.empty}>
                Still spørsmål om regler, vedtekter eller praktisk informasjon i borettslaget
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  ...styles.msg,
                  alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                  background: m.role === "user" ? "#2563eb" : "#f3f4f6",
                  color: m.role === "user" ? "white" : "#111827",
                }}
              >
                {m.text}
              </div>
            ))}

            {loading && (
              <div style={styles.typing}>Søker i dokumentene…</div>
            )}
          </div>

          <div style={styles.inputBar}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Spør borettslaget..."
              style={styles.chatInput}
            />
            <button onClick={() => askQuestion()} style={styles.send}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ----------------------------
const styles = {
  bg: {
    height: "100vh",
    background: "#f5f7fb",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    fontFamily: "Inter, Arial",
  },
  shell: {
    width: "95%",
    height: "92vh",
    display: "flex",
    borderRadius: 16,
    overflow: "hidden",
    background: "white",
  },
  sidebar: {
    width: 320,
    padding: 16,
    borderRight: "1px solid #eee",
  },
  logo: {
    fontSize: 18,
    fontWeight: 700,
    marginBottom: 12,
  },
  roleSwitch: {
    width: "100%",
    padding: 8,
    marginBottom: 10,
    borderRadius: 8,
    border: "1px solid #ddd",
    background: "#fff",
    cursor: "pointer",
    fontSize: 12,
  },
  role: {
    fontSize: 12,
    marginBottom: 12,
    color: "#555",
  },
  card: {
    padding: 12,
    border: "1px solid #eee",
    borderRadius: 10,
    marginBottom: 12,
  },
  label: {
    fontSize: 11,
    color: "#666",
    marginBottom: 6,
  },
  smallText: {
    fontSize: 11,
    wordBreak: "break-all",
  },
  button: {
    marginTop: 10,
    width: "100%",
    padding: 10,
    background: "#111",
    color: "white",
    borderRadius: 8,
    border: "none",
  },
  exampleBtn: {
    width: "100%",
    marginTop: 6,
    padding: 8,
    fontSize: 12,
    textAlign: "left",
    border: "1px solid #eee",
    borderRadius: 8,
    background: "#fafafa",
    cursor: "pointer",
  },
  main: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
  },
  topbar: {
    padding: 14,
    borderBottom: "1px solid #eee",
    fontWeight: 600,
  },
  chat: {
    flex: 1,
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  msg: {
    padding: 12,
    borderRadius: 12,
    maxWidth: "65%",
  },
  empty: {
    marginTop: 40,
    textAlign: "center",
    color: "#999",
  },
  typing: {
    fontSize: 12,
    color: "#777",
  },
  inputBar: {
    display: "flex",
    padding: 12,
    borderTop: "1px solid #eee",
  },
  chatInput: {
    flex: 1,
    padding: 10,
    borderRadius: 10,
    border: "1px solid #ddd",
  },
  send: {
    marginLeft: 10,
    padding: "10px 16px",
    borderRadius: 10,
    background: "#2563eb",
    color: "white",
    border: "none",
  },
};