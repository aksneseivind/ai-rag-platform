import { useRef, useState } from "react";

const API =
  import.meta.env.VITE_API_URL ||
  "https://ai-rag-platform.onrender.com";

export default function App() {
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [userId] = useState(() => {
    let id = localStorage.getItem("user_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("user_id", id);
    }
    return id;
  });

  const [role, setRole] = useState(() => {
    return localStorage.getItem("role") || "resident";
  });

  const toggleRole = () => {
    const newRole = role === "admin" ? "resident" : "admin";
    setRole(newRole);
    localStorage.setItem("role", newRole);
  };

  const quickQuestions = [
    "Når er det ro i bygget?",
    "Kan jeg ha husdyr i leiligheten?",
    "Hva gjelder ved oppussing?",
    "Hvor kaster jeg restavfall?",
    "Hvem kontakter jeg ved skade eller feil?",
  ];

  // =========================
  // UPLOAD FIXED
  // =========================
  const uploadPDF = async () => {
    if (!file) {
      alert("Velg en PDF først");
      return;
    }

    try {
      setUploading(true);

      const formData = new FormData();
      formData.append("file", file);

      // IMPORTANT: FastAPI expects Form field, not header
      formData.append("user_id", userId);

      console.log("Uploading to:", `${API}/upload`);

      const res = await fetch(`${API}/upload`, {
        method: "POST",
        body: formData,
      });

      const text = await res.text();

      if (!res.ok) {
        console.error("UPLOAD ERROR:", text);
        throw new Error(`Upload failed: ${res.status}`);
      }

      const data = JSON.parse(text);

      alert(`Upload OK ✔ (${data.chunks} chunks)`);

      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

    } catch (err) {
      console.error(err);
      alert(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // =========================
  // CHAT FIXED
  // =========================
  const askQuestion = async (overrideQuestion = null) => {
    const q = overrideQuestion ?? question;
    if (!q || !q.trim()) return;

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

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data?.detail || `Chat failed ${res.status}`);
      }

      setMessages((p) => [
        ...p,
        { role: "bot", text: data.answer || "Ingen respons" },
      ]);
    } catch (err) {
      console.error(err);
      setMessages((p) => [
        ...p,
        { role: "bot", text: "Kunne ikke kontakte server" },
      ]);
    } finally {
      setLoading(false);
      setQuestion("");
    }
  };

  return (
    <div>
      <h3>Borettslagsassistent OK frontend</h3>

      <input type="file" onChange={(e) => setFile(e.target.files?.[0])} />

      <button onClick={uploadPDF} disabled={!file || uploading}>
        {uploading ? "Laster opp..." : "Last opp PDF"}
      </button>

      <hr />

      <input
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
      />

      <button onClick={() => askQuestion()}>Send</button>

      {loading && <p>Søker...</p>}

      {messages.map((m, i) => (
        <p key={i}>
          <b>{m.role}:</b> {m.text}
        </p>
      ))}
    </div>
  );
}