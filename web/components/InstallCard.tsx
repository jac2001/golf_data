"use client";

/**
 * InstallCard — the one-time "get pick reminders" card after a first pick.
 * =========================================================================
 * Gathers this device's facts (DeviceState), asks lib/installPrompt.ts
 * cardStep() which card to show, and renders it. All the "when" rules
 * live in cardStep; this file only measures and acts.
 *
 * Fails closed: if cardStep throws (or anything here does), the card
 * simply doesn't show. A missing nudge is fine; a broken page is not.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { CARD_COPY, cardStep } from "@/lib/installPrompt";
import type { CardStep, DeviceState, Platform } from "@/lib/installPrompt";
import { PICKED_EVENT, currentEndpoint, hasPicked, pushSupported, subscribeThisDevice } from "@/lib/pushClient";

const DISMISS_KEY = "ge-install-card";

/** Chrome's install prompt event (not in TypeScript's DOM types). */
type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

function detectPlatform(): Platform {
  const ua = navigator.userAgent;
  // iPadOS reports itself as a Mac; the touch points give it away.
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/.test(ua)) return "android";
  return "desktop";
}

function isInstalled(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function readDismissals(): { count: number; at: Date | null } {
  try {
    const d = JSON.parse(localStorage.getItem(DISMISS_KEY) ?? "{}");
    return { count: Number(d.count) || 0, at: d.at ? new Date(d.at) : null };
  } catch { return { count: 0, at: null }; }
}

export default function InstallCard() {
  const { isSignedIn, getToken } = useAuth();
  const [step, setStep] = useState<CardStep>("none");
  const [platform, setPlatform] = useState<Platform>("desktop");
  const [busy, setBusy] = useState(false);
  const deferred = useRef<InstallPromptEvent | null>(null);
  const shownLogged = useRef<Set<string>>(new Set());

  const api = useCallback(async (url: string, init: RequestInit = {}) => {
    const token = await getToken();
    const res = await fetch(url, {
      ...init,
      headers: { ...(init.headers as Record<string, string> | undefined), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
    if (!res.ok) throw new Error(String(res.status));
    return res.json().catch(() => ({}));
  }, [getToken]);

  const log = useCallback((event: string, props: Record<string, unknown>) => {
    api("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, props }),
    }).catch(() => { /* measurement never matters more than the page */ });
  }, [api]);

  const refresh = useCallback(async () => {
    try {
      const p = detectPlatform();
      const dismissed = readDismissals();
      const state: DeviceState = {
        platform: p,
        installed: isInstalled(),
        canPromptInstall: deferred.current !== null,
        notifications: pushSupported() ? Notification.permission : "unsupported",
        subscribed: (await currentEndpoint()) !== "",
        hasPicked: hasPicked(),
        dismissCount: dismissed.count,
        lastDismissedAt: dismissed.at,
      };
      setPlatform(p);
      setStep(cardStep(state, new Date()));
    } catch {
      setStep("none");
    }
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    const onPrompt = (e: Event) => { e.preventDefault(); deferred.current = e as InstallPromptEvent; refresh(); };
    const onInstalled = () => { deferred.current = null; refresh(); };
    const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener(PICKED_EVENT, refresh);
    document.addEventListener("visibilitychange", onVisible);
    refresh();
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener(PICKED_EVENT, refresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [isSignedIn, refresh]);

  useEffect(() => {
    if (step !== "none" && !shownLogged.current.has(step)) {
      shownLogged.current.add(step);
      log("install_card_shown", { step, platform });
    }
  }, [step, platform, log]);

  function dismiss(accepted = false) {
    const d = readDismissals();
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify({ count: d.count + 1, at: new Date().toISOString() })); } catch { /* fine */ }
    if (!accepted) log("install_card_dismissed", { step, platform, count: d.count + 1 });
    setStep("none");
  }

  async function act() {
    setBusy(true);
    try {
      if (step === "install_ios") {
        // We can't install for them on iPhone; "Got it" means they've read
        // the steps. Counts toward the snooze so it doesn't reappear daily.
        log("install_card_accepted", { step, platform });
        dismiss(true);
      } else if (step === "install_prompt" && deferred.current) {
        await deferred.current.prompt();
        const { outcome } = await deferred.current.userChoice;
        deferred.current = null;
        if (outcome === "accepted") log("install_card_accepted", { step, platform });
        await refresh();
      } else if (step === "ask_reminders") {
        const endpoint = await subscribeThisDevice(api);
        if (endpoint) {
          log("install_card_accepted", { step, platform });
          log("reminders_enabled", { platform, installed: isInstalled() });
        }
        await refresh();
      }
    } catch {
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (step === "none") return null;
  const copy = CARD_COPY[step];

  return (
    <div role="dialog" aria-label={copy.title} style={{
      position: "fixed", left: 12, right: 12, bottom: 12, zIndex: 999,
      maxWidth: 440, margin: "0 auto",
      background: "var(--bc-raised)", color: "var(--bc-text)",
      border: "1px solid var(--bc-line-hi)", borderRadius: 10,
      boxShadow: "0 6px 24px rgba(0,0,0,0.5)", padding: "14px 16px",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 800, marginBottom: 4 }}>{copy.title}</div>
          <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.88em)", lineHeight: 1.5 }}>
            {step === "install_ios" ? <IosSteps /> : copy.body}
          </div>
        </div>
        <button onClick={() => dismiss()} aria-label="Not now" style={{
          background: "transparent", border: "none", color: "var(--bc-muted)",
          fontSize: "1.3em", lineHeight: 1, cursor: "pointer", padding: 4,
        }}>×</button>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button onClick={act} disabled={busy} style={{
          flex: 1, cursor: "pointer", fontFamily: "inherit", fontWeight: 800,
          background: "var(--bc-yellow)", color: "#081f14", border: "none",
          borderRadius: 6, padding: "11px 14px", fontSize: "max(var(--fs-min), 0.9em)",
        }}>{busy ? "…" : copy.action}</button>
        <button onClick={() => dismiss()} style={{
          cursor: "pointer", fontFamily: "inherit", fontWeight: 700,
          background: "transparent", color: "var(--bc-muted)",
          border: "1px solid var(--bc-line)", borderRadius: 6, padding: "11px 14px",
          fontSize: "max(var(--fs-min), 0.9em)",
        }}>Not now</button>
      </div>
    </div>
  );
}

/** The real steps, with Safari's Share glyph drawn so people can find it. */
function IosSteps() {
  const share = (
    <svg width="14" height="16" viewBox="0 0 14 16" aria-label="Share" style={{ verticalAlign: "-2px", margin: "0 2px" }}>
      <path d="M7 1v9M4 4l3-3 3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 6.5H2.5v8h9v-8h-2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
  return (
    <ol style={{ margin: 0, paddingLeft: 18 }}>
      <li>Tap Share {share} in Safari&apos;s toolbar</li>
      <li>Choose <b>Add to Home Screen</b></li>
      <li>Open Golf Edge from your home screen; we&apos;ll ask about reminders there</li>
    </ol>
  );
}
