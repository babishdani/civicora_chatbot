import { useState, useRef, useEffect } from "react";
import {
  Bot,
  Minus,
  Send,
  FileText,
  Droplets,
  BriefcaseBusiness,
  ChevronDown,
  RefreshCw,
  Heart,
  HandHeart,
  Users,
} from "lucide-react";

import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const SUGGESTION_DELAY = 10000;

// Audio files from public/sounds/
const sendAudio = new Audio("/sounds/send.mp3");
const responseAudio = new Audio("/sounds/response.mp3");

sendAudio.preload = "auto";
responseAudio.preload = "auto";

sendAudio.volume = 0.35;
responseAudio.volume = 0.4;

function playSound(audio) {
  try {
    audio.currentTime = 0;

    const playback = audio.play();

    if (playback && typeof playback.catch === "function") {
      playback.catch((error) => {
        console.warn("Sound playback was blocked:", error);
      });
    }
  } catch (error) {
    console.warn("Unable to play sound:", error);
  }
}

// Existing quick services
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
    message: "Show me the available blood donors.",
  },
  {
    title: "Job Fairs",
    description: "Explore job fair information",
    icon: BriefcaseBusiness,
    message: "Tell me about available job fairs.",
  },
];

// Citizen-service suggestions
const suggestedQuestions = [
  {
    label: "Children Support",
    question: "I need help with children support",
    icon: Heart,
  },
  {
    label: "Volunteer Register",
    question: "I want to register as a volunteer",
    icon: HandHeart,
  },
  {
    label: "Blood Donor Request",
    question: "I need blood",
    icon: Droplets,
  },
  {
    label: "Medical Camp",
    question: "Tell me about medical camps",
    icon: BriefcaseBusiness,
  },
  {
    label: "Meet Your MLA",
    question: "I want to meet the MLA",
    icon: Users,
  },
  {
    label: "Constituency Updates",
    question: "Show constituency events, development work, public events and ward-level progress",
    icon: FileText,
  },
  {
    label: "Livelihood & SHG",
    question: "Tell me about livelihood support, SHG, employment and placements",
    icon: BriefcaseBusiness,
  },
];

function getMessageTime() {
  return new Date().toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export default function App() {
  const isEmbed =
    new URLSearchParams(window.location.search).get("embed") === "1";

  const [isOpen, setIsOpen] = useState(isEmbed);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [showServices, setShowServices] = useState(true);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionsDismissed, setSuggestionsDismissed] =
    useState(false);

  const chatBodyRef = useRef(null);
  const inputRef = useRef(null);
  const loadingRef = useRef(false);
  const scrollTimerRef = useRef(null);
  const [conversationId, setConversationId] = useState(
  () => crypto.randomUUID());

  const suggestionsAreVisible =
    showSuggestions && !suggestionsDismissed && !loading;

  // Scroll helper: wait until the layout has updated before scrolling.
  function scrollChatToBottom(behavior = "smooth") {
    const chatBody = chatBodyRef.current;

    if (!chatBody) return;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const currentChatBody = chatBodyRef.current;

        if (!currentChatBody) return;

        currentChatBody.scrollTo({
          top: currentChatBody.scrollHeight,
          behavior,
        });
      });
    });
  }

  // Scroll when messages or loading state changes.
  useEffect(() => {
    scrollChatToBottom("smooth");
  }, [messages, loading]);

  // IMPORTANT:
  // Suggestions change the available height of the chat body.
  // Scroll again after the suggestions transition has completed.
  useEffect(() => {
    if (scrollTimerRef.current) {
      clearTimeout(scrollTimerRef.current);
    }

    if (!isOpen || messages.length === 0) {
      return undefined;
    }

    scrollChatToBottom("auto");

    // Allow CSS max-height/opacity transition to finish.
    scrollTimerRef.current = setTimeout(() => {
      scrollChatToBottom("smooth");
    }, 300);

    return () => {
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
      }
    };
  }, [
    isOpen,
    messages.length,
    suggestionsAreVisible,
  ]);

  // Focus input when the chat opens.
  useEffect(() => {
    if (isOpen && !loading) {
      inputRef.current?.focus();
    }
  }, [isOpen, loading]);

  // Automatically show suggestions after the configured delay.
  useEffect(() => {
    if (messages.length === 0 || loading || !isOpen) {
      setShowSuggestions(false);
      return undefined;
    }

    setShowSuggestions(false);

    const timer = setTimeout(() => {
      setShowSuggestions(true);
    }, SUGGESTION_DELAY);

    return () => clearTimeout(timer);
  }, [messages, loading, isOpen]);

  function refreshChat() {
    if (loadingRef.current) return;

    setMessages([]);
    setInput("");
    setShowServices(true);
    setShowSuggestions(false);
    setSuggestionsDismissed(false);
    setConversationId(crypto.randomUUID());

    if (scrollTimerRef.current) {
      clearTimeout(scrollTimerRef.current);
    }

    inputRef.current?.focus();
  }

  async function sendMessage(text, isRetry = false) {
    const question = (text ?? input).trim();

    if (!question || loadingRef.current) return;

    loadingRef.current = true;
    setLoading(true);
    setShowSuggestions(false);
    setSuggestionsDismissed(false);

    if (!isRetry) {
      setMessages((oldMessages) => [
        ...oldMessages,
        {
          role: "user",
          text: question,
          time: getMessageTime(),
        },
      ]);

      playSound(sendAudio);
      setInput("");
      setShowServices(false);
    }

    try {
      const controller = new AbortController();

      const timeoutId = setTimeout(() => {
        controller.abort();
      }, 45000);

      let response;

      try {
        response = await fetch(`${API_URL}/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question,
            conversation_id: conversationId,
          }),
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

      // Preserve the existing response delay.
      await new Promise((resolve) => setTimeout(resolve, 2000));

      playSound(responseAudio);

      setMessages((oldMessages) => [
        ...oldMessages,
        {
          role: "assistant",
          text: answer,
          time: getMessageTime(),
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
          time: getMessageTime(),
          isError: true,
          retryQuestion: question,
        },
      ]);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }

  // Render bold text and clickable URLs from chatbot responses.
  function renderMessageText(text) {
    const parts = text.split(/(\*\*.*?\*\*|https?:\/\/[^\s]+)/g);

    return parts.map((part, index) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={index}>
            {part.slice(2, -2)}
          </strong>
        );
      }

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

  // Services button controls the suggestion visibility.
  function toggleServices() {
    setShowServices((visible) => !visible);

    setShowSuggestions((visible) => !visible);
    setSuggestionsDismissed(false);

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        scrollChatToBottom("smooth");
      });
    });
  }

  return (
    <>
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
          <header className="chat-header civicora-header">
            <div className="chat-brand-icon">
              <Bot size={26} />
            </div>

            <div className="chat-brand-text">
              <strong className="civicora-title">Civicora</strong>
              <span>
                <i />
                Your Digital Citizen Assistant
              </span>
            </div>

            <button
              type="button"
              className="chat-header-button"
              onClick={refreshChat}
              disabled={loading}
              aria-label="Refresh chat"
              title="Refresh chat"
            >
              <RefreshCw size={19} />
            </button>

            {!isEmbed && (
              <button
                type="button"
                className="chat-header-button"
                onClick={() => setIsOpen(false)}
                aria-label="Minimize chatbot"
                title="Minimize"
              >
                <Minus size={22} />
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
                className={`message-row message-arrive ${
                  message.role === "user"
                    ? "message-user"
                    : "message-assistant"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="message-avatar">
                    <img
                      src="/civicora-chatbot-icon.png"
                      alt="Civicora assistant"
                      className="message-avatar-logo"
                    />
                  </div>
                )}

                <div className="message-content">
                  <div
                    className={`message-bubble ${
                      message.isError ? "message-error" : ""
                    }`}
                  >
                    {renderMessageText(message.text)}
                  </div>

                  <time className="message-time">
                    {message.time}
                  </time>

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

                {message.role === "user" && (
                  <div
                    className="user-message-avatar"
                    aria-label="User"
                    title="User"
                  >
                    U
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div
                className="message-row message-assistant"
                role="status"
                aria-label="Loading response"
              >
                <div className="message-avatar">
                  <Bot size={17} />
                </div>

                <div className="minimal-thinking minimal-thinking-icon">
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

          {messages.length > 0 && (
            <section
              className={`compact-suggestions ${
                suggestionsAreVisible
                  ? "suggestions-visible"
                  : "suggestions-hidden"
              }`}
              aria-hidden={!suggestionsAreVisible}
            >
              <div className="suggestions-container">
                <div className="suggestion-links">
                  {suggestedQuestions.map(
                    ({ label, question, icon: Icon }) => (
                      <button
                        type="button"
                        key={label}
                        onClick={() => sendMessage(question)}
                        disabled={!suggestionsAreVisible}
                        tabIndex={suggestionsAreVisible ? 0 : -1}
                      >
                        <Icon size={15} />
                        {label}
                      </button>
                    )
                  )}
                </div>
              </div>
            </section>
          )}

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
              placeholder="Ask about citizen services..."
              aria-label="Type your question"
              disabled={loading}
            />

            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || loading}
              aria-label="Send message"
            >
              <Send size={20} />
            </button>
          </form>

          <footer className="chat-footer">
            <span>Powered by Alo infotech</span>

            <div className="footer-actions">
              <button
                type="button"
                onClick={toggleServices}
                aria-expanded={showServices}
                aria-label="Toggle services and suggestions"
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