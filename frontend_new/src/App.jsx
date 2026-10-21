
import { useState, useRef, useEffect } from "react";

import {
  Bot,
  X,
  Send,
  FileText,
  Droplets,
  BriefcaseBusiness,
  Sparkles,
  ChevronDown,
  RefreshCw,
} from "lucide-react";

import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const services = [
  {
    title: "Grievances",
    description: "Report or check a grievance",
    icon: FileText,
    message: "How can I report a grievance?",
  },
  {
    title: "Blood Donors",
    description: "Access blood donor services",
    icon: Droplets,
    message: "How can I access the blood donor service?",
  },
  {
    title: "Job Fairs",
    description: "Explore job fair information",
    icon: BriefcaseBusiness,
    message: "Tell me about available job fairs.",
  },
];

export default function App() {
  // Detect whether the chatbot is embedded in another website.
  const isEmbed =
    new URLSearchParams(window.location.search).get("embed") === "1";

  // In embed mode, open the chat interface immediately.
  const [isOpen, setIsOpen] = useState(isEmbed);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [showServices, setShowServices] = useState(true);

  const chatBodyRef = useRef(null);
  const inputRef = useRef(null);
  const loadingRef = useRef(false);

  useEffect(() => {
    const chatBody = chatBodyRef.current;

    if (chatBody) {
      chatBody.scrollTo({
        top: chatBody.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, loading]);

  useEffect(() => {
    if (isOpen && !loading) {
      inputRef.current?.focus();
    }
  }, [isOpen, loading]);

  async function sendMessage(text, isRetry = false) {
    const question = (text ?? input).trim();

    if (!question || loadingRef.current) return;

    loadingRef.current = true;
    setLoading(true);

    if (!isRetry) {
      setMessages((oldMessages) => [
        ...oldMessages,
        { role: "user", text: question },
      ]);

      setInput("");
      setShowServices(false);
    }

    try {
      const controller = new AbortController();

      const timeoutId = setTimeout(
        () => controller.abort(),
        45000
      );

      let response;

      try {
        response = await fetch(`${API_URL}/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ question }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutId);
      }

      let data;

      try {
        data = await response.json();
      } catch {
        throw new Error(
          "The server returned an invalid response. Please try again."
        );
      }

      if (!response.ok) {
        throw new Error(
          data.detail ||
            data.message ||
            "Civicora is temporarily unavailable. Please try again."
        );
      }

      const answer =
        data.answer ||
        data.response ||
        data.message ||
        "Please contact the citizen service team for assistance.";

      setMessages((oldMessages) => [
        ...oldMessages,
        {
          role: "assistant",
          text: answer,
          isError: false,
        },
      ]);
    } catch (error) {
      const errorMessage =
        error.name === "AbortError"
          ? "The request took too long. Please try again."
          : error.message ||
            "Unable to connect right now. Please try again later.";

      setMessages((oldMessages) => [
        ...oldMessages,
        {
          role: "assistant",
          text: errorMessage,
          isError: true,
          retryQuestion: question,
        },
      ]);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }

  function renderMessageText(text) {
    const parts = text.split(/(https?:\/\/[^\s]+)/g);

    return parts.map((part, index) => {
      if (/^https?:\/\//.test(part)) {
        const url = part.replace(/[.,!?]+$/, "");
        const trailingText = part.slice(url.length);

        return (
          <span key={index}>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="chat-link"
            >
              {url}
            </a>
            {trailingText}
          </span>
        );
      }

      return <span key={index}>{part}</span>;
    });
  }

  return (
    <>
      {/* Hide the internal launcher in embedded mode. */}
      {!isEmbed && !isOpen && (
        <button
          type="button"
          className="chat-launcher"
          onClick={() => setIsOpen(true)}
          aria-label="Open Civicora chatbot"
        >
          <Bot size={27} />
          <span className="launcher-dot" />
        </button>
      )}

      {isOpen && (
        <section
          className={`chat-widget ${
            isEmbed ? "chat-widget-embed" : ""
          }`}
          aria-label="Civicora citizen assistant"
          style={
            isEmbed
              ? {
                  position: "relative",
                  inset: "auto",
                  width: "100%",
                  height: "100%",
                  maxHeight: "100%",
                  minHeight: 0,
                  borderRadius: 0,
                  boxShadow: "none",
                  display: "flex",
                  flexDirection: "column",
                }
              : undefined
          }
        >
          <header className="chat-header">
            <div className="chat-brand-icon">
              <Bot size={26} />
            </div>

            <div className="chat-brand-text">
              <strong>Civicora</strong>
              <span>
                <i />
                Your Digital Citizen Assistant
              </span>
            </div>

            {/* The parent website's orange icon controls closing. */}
            {!isEmbed && (
              <button
                type="button"
                className="chat-header-button"
                onClick={() => setIsOpen(false)}
                aria-label="Close chatbot"
              >
                <X size={22} />
              </button>
            )}
          </header>

          <div
            className="chat-body"
            ref={chatBodyRef}
            style={
              isEmbed
                ? {
                    flex: "1 1 0",
                    minHeight: 0,
                    overflowY: "auto",
                  }
                : undefined
            }
          >
            {messages.length === 0 && (
              <div className="welcome-section">
                <div className="welcome-avatar">
                  <Sparkles size={23} />
                </div>

                <span className="welcome-eyebrow">
                  WELCOME TO CIVICORA
                </span>

                <h2>Vanakkam! 👋</h2>

                <p>
                  Your digital companion for Ottapidaram
                  citizen services. How can I help you today?
                </p>
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`message-row ${
                  message.role === "user"
                    ? "message-user"
                    : "message-assistant"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="message-avatar">
                    <Bot size={17} />
                  </div>
                )}

                <div>
                  <div className="message-bubble">
                    {renderMessageText(message.text)}
                  </div>

                  {message.isError && (
                    <button
                      type="button"
                      className="retry-button"
                      disabled={loading}
                      onClick={() =>
                        sendMessage(message.retryQuestion, true)
                      }
                    >
                      <RefreshCw size={14} />
                      Retry
                    </button>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="message-row message-assistant">
                <div className="message-avatar">
                  <Bot size={17} />
                </div>

                <div
                  className="minimal-thinking"
                  aria-label="Civicora is thinking"
                >
                  <span>Civicora is thinking</span>

                  <div className="thinking-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}

            {showServices && messages.length === 0 && (
              <div className="service-list">
                <span className="service-list-label">
                  QUICK SERVICES
                </span>

                {services.map(
                  ({ title, description, icon: Icon, message }) => (
                    <button
                      type="button"
                      className="service-card"
                      key={title}
                      onClick={() => sendMessage(message)}
                      disabled={loading}
                    >
                      <span
                        className={`service-icon service-${title
                          .toLowerCase()
                          .replace(" ", "-")}`}
                      >
                        <Icon size={20} />
                      </span>

                      <span className="service-copy">
                        <strong>{title}</strong>
                        <small>{description}</small>
                      </span>

                      <span className="service-arrow">›</span>
                    </button>
                  )
                )}
              </div>
            )}
          </div>

          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask Civicora anything..."
              aria-label="Type your question"
              disabled={loading}
            />

            <button
              type="submit"
              disabled={!input.trim() || loading}
              aria-label="Send message"
            >
              <Send size={19} />
            </button>
          </form>

          <footer className="chat-footer">
            <span>Powered by Civicora AI</span>

            <div className="footer-actions">
              <button
                type="button"
                onClick={() =>
                  setShowServices((visible) => !visible)
                }
                aria-expanded={showServices}
              >
                Services <ChevronDown size={14} />
              </button>
            </div>
          </footer>
        </section>
      )}
    </>
  );
}
