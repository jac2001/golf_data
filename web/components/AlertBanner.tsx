"use client";

/**
 * AlertBanner — Live tournament alert toasts
 * ==========================================
 * Polls GET /api/alerts every 30s. When new alerts arrive, stacks them as
 * floating cards in the bottom-right corner. Each card auto-dismisses after 8s.
 *
 * Severity colours:
 *   high   → green border (your pick entering top 5 / taking the lead)
 *   normal → blue border (top 10 entry, big move, leader change)
 *   low    → grey border (other field events)
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { getAlerts, LiveAlert } from "@/lib/api";

const POLL_MS    = 30_000;
const DISMISS_MS = 8_000;

const SEV_COLORS: Record<string, { border: string; bg: string; dot: string }> = {
  high:   { border: "#00c44f", bg: "#061a0e", dot: "#00c44f" },
  normal: { border: "#4cb8ff", bg: "#061220", dot: "#4cb8ff" },
  low:    { border: "#3a5060", bg: "#091520", dot: "#3a5060" },
};

type ToastItem = LiveAlert & { expires: number };

export default function AlertBanner() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const poll = useCallback(async () => {
    try {
      const { alerts } = await getAlerts(true);
      if (!alerts.length) return;
      const now = Date.now();
      setToasts(prev => {
        // Deduplicate: don't add an alert already visible
        const existingIds = new Set(prev.map(t => t.id));
        const fresh = alerts.filter(a => !existingIds.has(a.id));
        if (!fresh.length) return prev;
        return [
          ...prev,
          ...fresh.map(a => ({ ...a, expires: now + DISMISS_MS })),
        ];
      });
    } catch {
      // silently ignore network errors
    }
  }, []);

  // Poll on mount and every 30s
  useEffect(() => {
    poll();
    timerRef.current = setInterval(poll, POLL_MS);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [poll]);

  // Auto-dismiss expired toasts every second
  useEffect(() => {
    const tick = setInterval(() => {
      const now = Date.now();
      setToasts(prev => prev.filter(t => t.expires > now));
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  if (!toasts.length) return null;

  return (
    <div style={{
      position: "fixed",
      bottom: 24,
      right: 24,
      zIndex: 9999,
      display: "flex",
      flexDirection: "column-reverse",
      gap: 10,
      maxWidth: 340,
    }}>
      {toasts.map(toast => {
        const colors = SEV_COLORS[toast.severity] ?? SEV_COLORS.low;
        const secLeft = Math.max(0, Math.round((toast.expires - Date.now()) / 1000));

        return (
          <div key={toast.id} style={{
            background:   colors.bg,
            border:       `1px solid ${colors.border}`,
            borderLeft:   `3px solid ${colors.border}`,
            borderRadius: 8,
            padding:      "10px 14px",
            boxShadow:    "0 4px 20px rgba(0,0,0,0.5)",
            animation:    "slideIn 0.2s ease-out",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: colors.dot, flexShrink: 0,
                    display: "inline-block",
                  }} />
                  <span style={{ fontSize: "0.82em", fontWeight: 700, color: "#dde6f5" }}>
                    {toast.title}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: "0.75em", color: "#7f8c8d", lineHeight: 1.4 }}>
                  {toast.body}
                </p>
              </div>
              <button
                onClick={() => dismiss(toast.id)}
                style={{
                  background: "none", border: "none", color: "#4a6080",
                  cursor: "pointer", fontSize: "1em", lineHeight: 1,
                  padding: 0, flexShrink: 0, marginTop: 1,
                }}
              >
                ×
              </button>
            </div>
            {/* Progress bar — visually shows time until auto-dismiss */}
            <div style={{ marginTop: 8, height: 2, background: "#0f2236", borderRadius: 1 }}>
              <div style={{
                height: "100%",
                background: colors.border,
                borderRadius: 1,
                width: `${(secLeft / (DISMISS_MS / 1000)) * 100}%`,
                transition: "width 0.9s linear",
              }} />
            </div>
          </div>
        );
      })}

      <style>{`
        @keyframes slideIn {
          from { opacity: 0; transform: translateX(20px); }
          to   { opacity: 1; transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
