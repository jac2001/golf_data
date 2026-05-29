"use client";

import { useState, useEffect, useRef } from "react";
import { streamChat, ChatMessage } from "@/lib/api";

const QUICK_QUESTIONS = [
  "Best bets this week?",
  "Who fits this course best?",
  "What's my lineup this week?",
  "How's the weather this week?",
  "Who's the model favorite and why?",
  "Show me the field overview",
];

const SOFT_LIMIT = 15;

function MarkdownText({ text }: { text: string }) {
  // Very light markdown: **bold**, `code`, and newlines
  const html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, '<code style="background:#0a1525;padding:1px 5px;border-radius:3px;font-family:monospace;font-size:0.9em;">$1</code>')
    .replace(/\n/g, "<br />");
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

function MessageBubble({ msg, isStreaming }: { msg: ChatMessage; isStreaming?: boolean }) {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 14,
    }}>
      {!isUser && (
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "#00c44f22", border: "1px solid #00c44f44",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, marginRight: 10, marginTop: 2,
          fontSize: "0.72em", fontWeight: 800, color: "#00c44f",
        }}>
          G
        </div>
      )}
      <div style={{
        maxWidth: "78%",
        background: isUser ? "#1e3a5f" : "#0d1a30",
        border: `1px solid ${isUser ? "#2a4f7f" : "#1e3a5f"}`,
        borderRadius: isUser ? "16px 16px 4px 16px" : "4px 16px 16px 16px",
        padding: "10px 14px",
        fontSize: "0.88em",
        color: "#dde6f5",
        lineHeight: 1.65,
      }}>
        {msg.content ? (
          <MarkdownText text={msg.content} />
        ) : isStreaming ? (
          <span style={{ color: "#4a6080" }}>▋</span>
        ) : null}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const [messages, setMessages]         = useState<ChatMessage[]>([]);
  const [input, setInput]               = useState("");
  const [streaming, setStreaming]       = useState(false);
  const [lastPlayers, setLastPlayers]   = useState<string[]>([]);
  const [error, setError]               = useState<string | null>(null);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const inputRef    = useRef<HTMLTextAreaElement>(null);
  const cancelRef   = useRef<(() => void) | null>(null);
  const userMsgCount = messages.filter(m => m.role === "user").length;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function extractPlayers(text: string): string[] {
    // Very simple: extract capitalized words that look like last names
    return Array.from(text.matchAll(/\b([A-Z][a-záéíóúñäöü]+(?:\s[A-Z][a-záéíóúñäöü]+)?)\b/g))
      .map(m => m[1])
      .filter(n => n.length > 3)
      .slice(0, 4);
  }

  async function send(query: string) {
    if (!query.trim() || streaming) return;
    setError(null);
    setInput("");

    const userMsg: ChatMessage = { role: "user", content: query.trim() };
    const history = [...messages, userMsg];
    setMessages([...history, { role: "assistant", content: "" }]);
    setStreaming(true);

    let full = "";
    cancelRef.current = streamChat(
      query,
      history,
      lastPlayers,
      (chunk) => {
        full += chunk;
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: full };
          return updated;
        });
      },
      () => {
        setStreaming(false);
        setLastPlayers(extractPlayers(full));
      },
      (err) => {
        setError(err);
        setStreaming(false);
        setMessages(prev => prev.slice(0, -1)); // remove empty assistant bubble
      },
    );
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  function clear() {
    if (cancelRef.current) { cancelRef.current(); cancelRef.current = null; }
    setMessages([]);
    setLastPlayers([]);
    setStreaming(false);
    setError(null);
  }

  const showLimitWarning = userMsgCount >= SOFT_LIMIT;

  return (
    <div style={{
      maxWidth: 800, margin: "0 auto",
      display: "flex", flexDirection: "column", height: "calc(100vh - 80px)",
    }}>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexShrink: 0 }}>
        <div>
          <h1 style={{ fontSize: "1.4em", fontWeight: 800, color: "#dde6f5", margin: 0 }}>
            Assistant
          </h1>
          <p style={{ color: "#4a6080", fontSize: "0.78em", margin: "3px 0 0" }}>
            Golf analytics chatbot · Haiku · context-aware
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clear}
            style={{
              background: "transparent", border: "1px solid #1e3a5f",
              borderRadius: 6, color: "#7f8c8d", padding: "5px 12px",
              fontSize: "0.78em", cursor: "pointer",
            }}
          >
            Clear chat
          </button>
        )}
      </div>

      {/* ── Message area ──────────────────────────────────────────────────── */}
      <div style={{
        flex: 1, overflowY: "auto", paddingRight: 4,
        display: "flex", flexDirection: "column",
      }}>

        {/* Empty state with quick questions */}
        {messages.length === 0 && (
          <div style={{ margin: "auto 0", paddingBottom: 24 }}>
            <div style={{
              textAlign: "center", color: "#4a6080",
              fontSize: "0.88em", marginBottom: 24,
            }}>
              Ask anything about this week's tournament, players, bets, or your lineup.
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
              {QUICK_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  style={{
                    background: "#0d1a30", border: "1px solid #1e3a5f",
                    borderRadius: 20, color: "#8ba0b8",
                    padding: "7px 14px", fontSize: "0.82em",
                    cursor: "pointer", transition: "border-color 0.15s, color 0.15s",
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Messages */}
        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            msg={msg}
            isStreaming={streaming && i === messages.length - 1 && msg.role === "assistant"}
          />
        ))}

        {/* Error */}
        {error && (
          <div style={{
            background: "#1a0d0d", border: "1px solid #5f1e1e", borderRadius: 8,
            padding: "10px 14px", color: "#e74c3c", fontSize: "0.82em", marginBottom: 12,
          }}>
            {error}
          </div>
        )}

        {/* Soft limit warning */}
        {showLimitWarning && (
          <div style={{
            background: "#1a1200", border: "1px solid #5f4a00", borderRadius: 8,
            padding: "8px 14px", color: "#f39c12", fontSize: "0.78em",
            marginBottom: 12, textAlign: "center",
          }}>
            Long conversation — consider clearing the chat to keep responses fast and costs low.
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input area ────────────────────────────────────────────────────── */}
      <div style={{
        flexShrink: 0, paddingTop: 12, borderTop: "1px solid #1e3a5f",
      }}>
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about bets, players, course fit, lineup…"
            rows={2}
            style={{
              flex: 1, background: "#0d1a30", border: "1px solid #1e3a5f",
              borderRadius: 10, color: "#dde6f5", padding: "10px 14px",
              fontSize: "0.88em", lineHeight: 1.5, resize: "none",
              outline: "none", fontFamily: "inherit",
            }}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || streaming}
            style={{
              background: input.trim() && !streaming ? "#00c44f" : "#1e3a5f",
              border: "none", borderRadius: 10, color: "#fff",
              padding: "10px 18px", fontSize: "0.88em", fontWeight: 700,
              cursor: input.trim() && !streaming ? "pointer" : "default",
              transition: "background 0.15s", flexShrink: 0, alignSelf: "stretch",
            }}
          >
            {streaming ? "…" : "Send"}
          </button>
        </div>
        <div style={{ fontSize: "0.65em", color: "#2a3a4a", marginTop: 6, textAlign: "right" }}>
          Enter to send · Shift+Enter for newline
          {userMsgCount > 0 && ` · ${userMsgCount} messages this session`}
        </div>
      </div>

    </div>
  );
}
