import { useEffect, useState } from "react";
import { supabase } from "./lib/supabase";

const API =
  import.meta.env.VITE_API_URL ||
  "https://ai-rag-platform.onrender.com";

export default function App() {

  // =========================
  // AUTH
  // =========================

  const [session, setSession] = useState(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] =
    useState("");

  useEffect(() => {
    supabase.auth
      .getSession()
      .then(({ data }) => {
        setSession(data.session);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session);
      }
    );

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  // =========================
  // APP STATE
  // =========================

  const [file, setFile] = useState(null);

  const [question, setQuestion] =
    useState("");

  const [messages, setMessages] =
    useState([]);

  const [loading, setLoading] =
    useState(false);

  // =========================
  // USER
  // =========================

  const userId =
    session?.user?.id || null;

   // =========================
// DEL 10 — PROFILE
// =========================

const [profile, setProfile] = useState(null);
const [profileLoading, setProfileLoading] = useState(true);

useEffect(() => {
  const loadProfile = async () => {
    if (!session?.user?.id) {
      setProfile(null);
      setProfileLoading(false);
      return;
    }

    setProfileLoading(true);

    try {
      const { data, error } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", session.user.id)
        .single();

      if (error) {
        console.error("Profile error:", error);
        setProfile(null);
      } else {
        setProfile(data);
      }
    } catch (err) {
      console.error("Profile fetch failed:", err);
      setProfile(null);
    } finally {
      setProfileLoading(false);
    }
  };

  loadProfile();
}, [session]);

  // =========================
  // ROLE SWITCH
  // =========================

  const [role, setRole] = useState(() => {
    return (
      localStorage.getItem("role") ||
      "resident"
    );
  });

  const toggleRole = () => {
    const newRole =
      role === "admin"
        ? "resident"
        : "admin";

    setRole(newRole);

    localStorage.setItem(
      "role",
      newRole
    );
  };

  // =========================
  // LOGIN
  // =========================

  const signIn = async () => {

    const { error } =
      await supabase.auth
        .signInWithPassword({
          email,
          password,
        });

    if (error) {
      alert(error.message);
    }
  };

  // =========================
  // LOGOUT
  // =========================

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  // =========================
  // QUICK QUESTIONS
  // =========================

  const quickQuestions = [
    "Når er det ro i bygget?",
    "Kan jeg ha husdyr i leiligheten?",
    "Hva gjelder ved oppussing?",
    "Hvor kaster jeg restavfall?",
    "Hvem kontakter jeg ved skade eller feil?",
  ];

  // =========================
// UPLOAD
// =========================

const uploadPDF = async () => {

  if (!file) return;

  if (!profile?.borettslag_id) {
    alert("Brukerdata ikke lastet enda – prøv igjen om et øyeblikk");
    return;
  }

  if (!userId) {
  alert("Bruker ikke klar enda – prøv igjen");
  return;
}

  try {

    const borettslagId = profile.borettslag_id;

    const formData = new FormData();

    formData.append("file", file);

    formData.append("user_id", userId);

    formData.append("borettslag_id", borettslagId);

    const res = await fetch(`${API}/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      throw new Error(`Upload failed (${res.status})`);
    }

    const data = await res.json();

    alert(`Dokument lastet opp ✔ (${data.chunks} chunks)`);

    setFile(null);

  } catch (err) {

    console.error(err);

    alert("Upload failed");
  }
};

 // =========================
// CHAT
// =========================

const askQuestion = async (overrideQuestion = null) => {

  const q = overrideQuestion || question;

  if (!q.trim()) return;

  if (!profile?.borettslag_id) {
    alert("Brukerdata ikke lastet enda – prøv igjen om et øyeblikk");
    return;
  }

  if (!userId) {
    alert("Bruker ikke klar enda – prøv igjen");
    return;
  }

  setMessages((prev) => [
    ...prev,
    {
      role: "user",
      text: q,
    },
  ]);

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
        borettslag_id: profile.borettslag_id,
      }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();

    setMessages((prev) => [
      ...prev,
      {
        role: "bot",
        text: data.answer || "Ingen respons",
      },
    ]);

  } catch (err) {

    console.error(err);

    setMessages((prev) => [
      ...prev,
      {
        role: "bot",
        text: "Kunne ikke kontakte server",
      },
    ]);

  } finally {
    setLoading(false);
    setQuestion("");
  }
};

  // =========================
  // LOGIN SCREEN
  // =========================

  if (!session) {

    return (
      <div style={styles.loginPage}>

        <div style={styles.loginCard}>

          <h2>
            🏢 Borettslagsassistent
          </h2>

          <input
            placeholder="E-post"
            value={email}
            onChange={(e) =>
              setEmail(e.target.value)
            }
            style={styles.loginInput}
          />

          <input
            type="password"
            placeholder="Passord"
            value={password}
            onChange={(e) =>
              setPassword(
                e.target.value
              )
            }
            style={styles.loginInput}
          />

          <button
            onClick={signIn}
            style={styles.loginButton}
          >
            Logg inn
          </button>

        </div>

      </div>
    );
  }

  // =========================
  // MAIN UI
  // =========================

  return (
    <div style={styles.bg}>

      <div style={styles.shell}>

        {/* SIDEBAR */}

        <div style={styles.sidebar}>

          <div style={styles.logo}>
            🏢 Borettslagsassistent
          </div>

          <button
            onClick={toggleRole}
            style={styles.roleSwitch}
          >
            Bytt rolle (DEV): {role}
          </button>

          <div style={styles.role}>
            Aktiv rolle:{" "}
            <b>
              {role === "admin"
                ? "Styret (admin)"
                : "Beboer"}
            </b>
          </div>

          <button
            onClick={signOut}
            style={styles.logoutBtn}
          >
            Logg ut
          </button>

          {/* ADMIN */}

          {role === "admin" && (
            <div style={styles.card}>

              <div style={styles.label}>
                Styret – dokumenthåndtering
              </div>

              <input
                type="file"
                accept=".pdf"
                onChange={(e) =>
                  setFile(
                    e.target.files?.[0]
                  )
                }
              />

              <button
                onClick={uploadPDF}
                disabled={!file}
                style={{
                  ...styles.button,
                  opacity:
                    !file ? 0.5 : 1,
                }}
              >
                Last opp PDF
              </button>

            </div>
          )}

          {/* QUESTIONS */}

          <div style={styles.card}>

            <div style={styles.label}>
              Vanlige spørsmål
            </div>

            {quickQuestions.map(
              (q, i) => (
                <button
                  key={i}
                  onClick={() =>
                    askQuestion(q)
                  }
                  style={
                    styles.exampleBtn
                  }
                >
                  {q}
                </button>
              )
            )}

          </div>

          {/* USER */}

          <div style={styles.card}>

            <div style={styles.label}>
              Innlogget bruker
            </div>

            <div style={styles.smallText}>
              {session.user.email}
            </div>

          </div>

        </div>

        {/* MAIN */}

        <div style={styles.main}>

          <div style={styles.topbar}>
            Søk i borettslagets dokumenter
          </div>

          <div style={styles.chat}>

            {messages.length === 0 && (
              <div style={styles.empty}>
                Still spørsmål om regler,
                vedtekter eller praktisk
                informasjon
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  ...styles.msg,

                  alignSelf:
                    m.role === "user"
                      ? "flex-end"
                      : "flex-start",

                  background:
                    m.role === "user"
                      ? "#2563eb"
                      : "#f3f4f6",

                  color:
                    m.role === "user"
                      ? "white"
                      : "#111827",
                }}
              >
                {m.text}
              </div>
            ))}

            {loading && (
              <div style={styles.typing}>
                Søker i dokumentene…
              </div>
            )}

          </div>

          <div style={styles.inputBar}>

           <input
  value={question}
  onChange={(e) =>
    setQuestion(e.target.value)
  }
  disabled={!profile?.borettslag_id || profileLoading}
  placeholder={
    profileLoading
      ? "Laster brukerdata..."
      : "Spør borettslaget..."
  }
  style={styles.chatInput}
  onKeyDown={(e) => {
    if (e.key === "Enter" && profile?.borettslag_id && !profileLoading) {
      askQuestion();
    }
  }}
/>
           <button
  onClick={() => askQuestion()}
  disabled={!profile?.borettslag_id || profileLoading}
  style={{
    ...styles.send,
    opacity:
      !profile?.borettslag_id || profileLoading
        ? 0.5
        : 1,
    cursor:
      !profile?.borettslag_id || profileLoading
        ? "not-allowed"
        : "pointer",
  }}
>
  Send
</button>

          </div>

        </div>

      </div>

    </div>
  );
}

// =========================
// STYLES
// =========================

const styles = {

  loginPage: {
    height: "100vh",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    background: "#f5f7fb",
  },

  loginCard: {
    width: 320,
    background: "white",
    padding: 24,
    borderRadius: 16,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },

  loginInput: {
    padding: 10,
    borderRadius: 8,
    border: "1px solid #ddd",
  },

  loginButton: {
    padding: 10,
    borderRadius: 8,
    border: "none",
    background: "#2563eb",
    color: "white",
    cursor: "pointer",
  },

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

  logoutBtn: {
    width: "100%",
    padding: 8,
    marginBottom: 12,
    borderRadius: 8,
    border: "none",
    background: "#ef4444",
    color: "white",
    cursor: "pointer",
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
    overflowY: "auto",
  },

  msg: {
    padding: 12,
    borderRadius: 12,
    maxWidth: "65%",
    whiteSpace: "pre-wrap",
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