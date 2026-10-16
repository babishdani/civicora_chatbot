import { useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  Plus,
  MessageSquare,
  LayoutDashboard,
  FileText,
  Droplets,
  BriefcaseBusiness,
  Settings,
  LogOut,
  Send,
  Sparkles,
  ArrowUpRight,
  ShieldCheck,
  CircleHelp,
  Menu,
  X,
  LockKeyhole,
  Smartphone,
  LoaderCircle,
} from "lucide-react";
import "./App.css";

const API_URL = (
  import.meta.env.VITE_API_URL ||
  "https://citizen-service-chatbot.onrender.com"
).replace(/\/+$/, "");

const suggestions = [
  {
    icon: FileText,
    title: "My grievances",
    description: "Check your complaints and status",
    question: "Show my grievances",
  },
  {
    icon: Droplets,
    title: "Blood donor services",
    description: "Find the blood donor service",
    question: "How can I access blood donor services?",
  },
  {
    icon: BriefcaseBusiness,
    title: "Job fairs",
    description: "Explore available job fairs",
    question: "Show me available job fairs",
  },
];

export default function App() {
  const [token, setToken] = useState(
    () => localStorage.getItem("citizen_access_token") || ""
  );

  const [role, setRole] = useState(
    () => localStorage.getItem("citizen_role") || "citizen"
  );

  const [mobile, setMobile] = useState("");
  const [loginError, setLoginError] = useState("");
  const [mobileError, setMobileError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [activeChat, setActiveChat] = useState("New conversation");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loading, setLoading] = useState(false);

  // Login function
  async function login(event) {
    event.preventDefault();

    setLoginError("");
    setMobileError("");

    const cleanMobile = mobile.trim();

    // Validate 10-digit Indian mobile number
    if (!/^[6-9]\d{9}$/.test(cleanMobile)) {
      setMobileError("Enter the correct mobile number.");
      return;
    }

    setLoginLoading(true);

    try {
      const response = await fetch(`${API_URL}/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          role,
          mobile_number: cleanMobile,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          data.detail ||
            data.message ||
            "Login failed. Please try again."
        );
      }

      if (!data.success || !data.access_token) {
        throw new Error(
          "The server did not return a valid login token."
        );
      }

      localStorage.setItem(
        "citizen_access_token",
        data.access_token
      );

      localStorage.setItem(
        "citizen_role",
        data.role || role
      );

      setToken(data.access_token);
      setRole(data.role || role);
      setMessages([]);
      setActiveChat("New conversation");
      setMobile("");
      setMobileError("");
    } catch (error) {
      setLoginError(
        error.message ||
          "Unable to connect to the server. Please try again."
      );
    } finally {
      setLoginLoading(false);
    }
  }

  // Logout function
  function logout() {
    localStorage.removeItem("citizen_access_token");
    localStorage.removeItem("citizen_role");

    setToken("");
    setMessages([]);
    setQuestion("");
    setActiveChat("New conversation");
    setLoginError("");
    setMobileError("");
  }

  // Start a new conversation
  function startNewChat() {
    setMessages([]);
    setQuestion("");
    setActiveChat("New conversation");
  }

  // Send message to chatbot API
  async function sendMessage(text = question) {
    const cleanQuestion = text.trim();

    if (!cleanQuestion || loading || !token) {
      return;
    }

    setMessages((previous) => [
      ...previous,
      {
        role: "user",
        content: cleanQuestion,
      },
    ]);

    setQuestion("");
    setLoading(true);

    setActiveChat(
      cleanQuestion.length > 30
        ? `${cleanQuestion.slice(0, 30)}...`
        : cleanQuestion
    );

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question: cleanQuestion,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (response.status === 401) {
        logout();
        setLoginError("Your session expired. Please log in again.");
        return;
      }

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to process your question."
        );
      }

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: data.answer || "I couldn't find an answer.",
        },
      ]);
    } catch (error) {
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            error.message ||
            "Unable to connect to the chatbot. Please try again.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // Login screen
  if (!token) {
    return (
      <div className="login-page">
        <div className="login-decoration login-decoration-one" />
        <div className="login-decoration login-decoration-two" />

        <motion.div
          className="login-card"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <div className="login-brand">
            <div className="login-brand-icon">
              <Bot size={29} />
            </div>

            <div>
              <div className="login-brand-name">
                Civic<span>AI</span>
              </div>

              <div className="login-brand-caption">
                CITIZEN SERVICE PORTAL
              </div>
            </div>
          </div>

          <div className="login-orb">
            <div className="login-orb-ring" />
            <Bot size={44} />
            <Sparkles
              className="login-orb-sparkle"
              size={20}
            />
          </div>

          <div className="login-heading">
            <span className="login-eyebrow">
              <ShieldCheck size={14} />
              SECURE ACCESS
            </span>

            <h1>Welcome back</h1>

            <p>
              Sign in to your account and let your civic assistant
              help you navigate citizen services.
            </p>
          </div>

          <form className="login-form" onSubmit={login}>
            <label htmlFor="role">Account type</label>

            <div className="role-selector">
              {["citizen", "admin", "commander"].map((item) => (
                <button
                  type="button"
                  key={item}
                  className={`role-option ${
                    role === item ? "selected" : ""
                  }`}
                  onClick={() => setRole(item)}
                >
                  {item.charAt(0).toUpperCase() + item.slice(1)}
                </button>
              ))}
            </div>

            <label htmlFor="mobile">
              Registered mobile number
            </label>

            <div className="login-input-wrap">
              <Smartphone size={18} />

              <input
                id="mobile"
                type="tel"
                inputMode="numeric"
                autoComplete="tel-national"
                placeholder="Enter your 10-digit mobile number"
                value={mobile}
                maxLength={10}
                pattern="[6-9][0-9]{9}"
                onChange={(event) => {
                  const digits = event.target.value
                    .replace(/\D/g, "")
                    .slice(0, 10);

                  setMobile(digits);
                  setMobileError("");
                  setLoginError("");
                }}
                aria-invalid={Boolean(mobileError)}
                aria-describedby={
                  mobileError ? "mobile-error" : undefined
                }
                required
              />
            </div>

            {mobileError && (
              <div
                id="mobile-error"
                className="login-error"
                role="alert"
              >
                {mobileError}
              </div>
            )}

            {loginError && (
              <div className="login-error" role="alert">
                {loginError}
              </div>
            )}

            <button
              type="submit"
              className="login-submit"
              disabled={loginLoading}
            >
              {loginLoading ? (
                <>
                  <LoaderCircle
                    className="spin-icon"
                    size={18}
                  />
                  Signing in...
                </>
              ) : (
                <>
                  Sign in securely
                  <ArrowUpRight size={18} />
                </>
              )}
            </button>
          </form>

          <div className="login-security">
            <LockKeyhole size={15} />
            <span>
              Your session is protected by server authentication.
            </span>
          </div>

          <p className="login-footer">
            By signing in, you agree to use citizen services
            responsibly.
          </p>
        </motion.div>

        <div className="login-bottom-brand">
          <ShieldCheck size={15} />
          Secure citizen services · CivicAI
        </div>
      </div>
    );
  }

  // Authenticated chatbot
  return (
    <div className="app-shell">
      <aside
        className={`sidebar ${
          sidebarOpen ? "" : "sidebar-hidden"
        }`}
      >
        <div className="brand">
          <div className="brand-icon">
            <Bot size={25} />
          </div>

          <div>
            <div className="brand-name">
              Civic<span>AI</span>
            </div>

            <div className="brand-caption">
              CITIZEN SERVICE PORTAL
            </div>
          </div>

          <button
            className="icon-button sidebar-close"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          >
            <X size={18} />
          </button>
        </div>

        <button
          className="new-chat-button"
          onClick={startNewChat}
        >
          <Plus size={18} />
          <span>New conversation</span>
        </button>

        <div className="nav-label">WORKSPACE</div>

        <nav className="nav-list">
          <button
            className="nav-item active"
            onClick={startNewChat}
          >
            <MessageSquare size={18} />
            <span>AI Assistant</span>
          </button>

          <button
            className="nav-item"
            onClick={() => sendMessage("Show my grievances")}
          >
            <LayoutDashboard size={18} />
            <span>My grievances</span>
          </button>

          <button
            className="nav-item"
            onClick={() =>
              sendMessage(
                "How can I access blood donor services?"
              )
            }
          >
            <Droplets size={18} />
            <span>Blood donor services</span>
          </button>

          <button
            className="nav-item"
            onClick={() => sendMessage("Show available job fairs")}
          >
            <BriefcaseBusiness size={18} />
            <span>Job fairs</span>
          </button>
        </nav>

        <div className="nav-label recent-label">
          RECENT CONVERSATIONS
        </div>

        <div className="history-list">
          {messages
            .filter((message) => message.role === "user")
            .slice(-5)
            .reverse()
            .map((message, index) => (
              <button
                key={`${message.content}-${index}`}
                className="history-item"
                onClick={() => setQuestion(message.content)}
                title={message.content}
              >
                <MessageSquare size={15} />
                <span>{message.content}</span>
              </button>
            ))}
        </div>

        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon">
              <CircleHelp size={18} />
            </div>

            <div>
              <strong>Need assistance?</strong>
              <p>We're here to help you.</p>
            </div>

            <ArrowUpRight size={15} />
          </div>

          <div className="profile-row">
            <div className="profile-avatar">
              {role.charAt(0).toUpperCase()}
            </div>

            <div className="profile-text">
              <strong>
                {role.charAt(0).toUpperCase() + role.slice(1)}
              </strong>
              <span>Authenticated session</span>
            </div>

            <button
              className="logout-button"
              onClick={logout}
              title="Logout"
              aria-label="Logout"
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            {!sidebarOpen && (
              <button
                className="icon-button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open sidebar"
              >
                <Menu size={20} />
              </button>
            )}

            <div className="breadcrumb">
              Workspace <span>/</span>{" "}
              <strong>AI Assistant</strong>
            </div>
          </div>

          <div className="topbar-right">
            <div className="status-pill">
              <span />
              API connected
            </div>

            <button
              className="icon-button"
              aria-label="Settings"
            >
              <Settings size={18} />
            </button>

            <div className="top-avatar">
              {role.charAt(0).toUpperCase()}
            </div>
          </div>
        </header>

        <section className="chat-scroll">
          {messages.length === 0 ? (
            <motion.div
              className="welcome-section"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55 }}
            >
              <div className="hero-glow" />

              <div className="hero-badge">
                <Sparkles size={14} />
                YOUR SMART CIVIC COMPANION
              </div>

              <div className="assistant-orb">
                <div className="orb-ring ring-one" />
                <div className="orb-ring ring-two" />

                <div className="orb-core">
                  <Bot size={51} strokeWidth={1.45} />
                  <span className="orb-sparkle sparkle-one">
                    ✦
                  </span>
                  <span className="orb-sparkle sparkle-two">
                    ✧
                  </span>
                </div>

                <div className="orb-shadow" />
              </div>

              <div className="welcome-banner">
                <div className="welcome-content">
                  <h1>
                    How can I help <span>you today?</span>
                  </h1>

                  <p className="welcome-copy">
                    Your one-stop assistant for citizen services.
                    Ask questions, track grievances, and find the
                    support you need.
                  </p>
                </div>

                <div className="welcome-robot">
                  <img
                    src="/civic-robot.png"
                    alt="CivicAI Robot"
                  />
                </div>
              </div>

              <div className="suggestion-grid">
                {suggestions.map(
                  ({
                    icon: Icon,
                    title,
                    description,
                    question: prompt,
                  }) => (
                    <motion.button
                      key={title}
                      className="suggestion-card"
                      onClick={() => sendMessage(prompt)}
                      whileHover={{ y: -5, scale: 1.015 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      <div
                        className={`suggestion-icon suggestion-icon-${suggestions.findIndex(
                          (item) => item.title === title
                        )}`}
                      >
                        <Icon size={21} />
                      </div>

                      <strong>{title}</strong>
                      <p>{description}</p>

                      <ArrowUpRight
                        size={17}
                        className="suggestion-arrow"
                      />
                    </motion.button>
                  )
                )}
              </div>

              <div className="trust-row">
                <ShieldCheck size={16} />
                <span>Private by design</span>
                <span className="trust-separator">·</span>
                <span>Secure citizen access</span>
              </div>
            </motion.div>
          ) : (
            <div className="conversation">
              <div className="conversation-heading">
                <div className="conversation-heading-icon">
                  <Sparkles size={18} />
                </div>

                <div>
                  <h2>{activeChat}</h2>
                  <p>Your conversation with CivicAI</p>
                </div>
              </div>

              {messages.map((message, index) => (
                <motion.div
                  key={`${index}-${message.role}`}
                  className={`message-row ${
                    message.role === "user" ? "user-row" : ""
                  }`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  {message.role === "assistant" && (
                    <div className="message-avatar">
                      <Bot size={19} />
                    </div>
                  )}

                  <div
                    className={`message-bubble ${
                      message.role === "user"
                        ? "user-bubble"
                        : "assistant-bubble"
                    } ${
                      message.error ? "error-bubble" : ""
                    }`}
                  >
                    {message.role === "assistant" && (
                      <div className="answer-label">
                        CIVICAI ASSISTANT
                      </div>
                    )}

                    <div className="message-content">
                      {message.content}
                    </div>
                  </div>

                  {message.role === "user" && (
                    <div className="user-avatar">You</div>
                  )}
                </motion.div>
              ))}

              {loading && (
                <div className="message-row">
                  <div className="message-avatar">
                    <Bot size={19} />
                  </div>

                  <div className="typing-bubble">
                    <span />
                    <span />
                    <span />
                    <small>
                      Thinking through your request...
                    </small>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        <footer className="composer-area">
          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <input
              value={question}
              onChange={(event) =>
                setQuestion(event.target.value)
              }
              placeholder="Ask anything about citizen services..."
              aria-label="Your message"
            />

            <div className="composer-end">
              <span className="composer-hint">
                Enter to send
              </span>

              <button
                type="submit"
                className="send-button"
                disabled={!question.trim() || loading}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
            </div>
          </form>

          <p className="disclaimer">
            <ShieldCheck size={13} />
            CivicAI can make mistakes. Please verify important
            information.
          </p>
        </footer>
      </main>
    </div>
  );
}