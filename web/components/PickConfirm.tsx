"use client";

/**
 * PickConfirm — the answer to "did my pick save?"
 * ===============================================
 * A complete entry gets a bottom sheet ("You're in"); a partial one gets
 * a small note that fades on its own. The words are Jack's
 * lib/pickConfirm.ts confirmCopy; this file only draws and times them.
 *
 * Closing it fires the "picked" signal (lib/pushClient markPicked), which
 * is what lets the install card appear: confirmation first, then the
 * install ask, never two bottom cards at once.
 */

import { useEffect } from "react";
import Sheet from "@/components/Sheet";
import { confirmCopy } from "@/lib/pickConfirm";
import type { ConfirmCopy, ConfirmInput } from "@/lib/pickConfirm";
import { eventStatusLine } from "@/lib/eventStatus";
import { lockAt } from "@/lib/lockTime";
import { currentEndpoint, markPicked, pushSupported } from "@/lib/pushClient";

const NOTE_MS = 2600;

/** Build the copy for a save. Never throws: a plain "Saved" beats nothing. */
export async function buildConfirm(o: {
  picked: string[]; needed: number; startDate: string; tour: "pga" | "euro";
  /** This pick's own lock when it isn't the event's (a Round Game round). */
  lock?: Date;
}): Promise<ConfirmCopy> {
  let lockDetail = "";
  try {
    const at = o.lock ?? lockAt(o.startDate, o.tour);
    if (at.getTime() > Date.now()) {          // a lock already passed says nothing
      lockDetail = eventStatusLine({ status: "open", tour: o.tour, startDate: o.startDate,
        lockAt: at, round: null }, new Date()).detail;
    }
  } catch { /* unknown lock: say nothing about it */ }
  let remindersOn: boolean | null = null;
  try { if (pushSupported()) remindersOn = (await currentEndpoint()) !== ""; } catch { /* unknown */ }
  const input: ConfirmInput = { picked: o.picked, needed: o.needed, lockDetail, remindersOn };
  try { return confirmCopy(input); }
  catch { return { title: "Saved", body: "", complete: o.picked.length >= o.needed }; }
}

export default function PickConfirm({ copy, onClose }: { copy: ConfirmCopy | null; onClose: () => void }) {
  const close = () => { onClose(); markPicked(); };

  useEffect(() => {
    if (!copy || copy.complete) return;
    const t = setTimeout(close, NOTE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [copy]);

  if (!copy) return null;

  if (!copy.complete) {
    return (
      <div role="status" aria-live="polite" style={{
        position: "fixed", left: 12, right: 12, bottom: "var(--bottom-offset)", zIndex: 999,
        maxWidth: 440, margin: "0 auto", background: "var(--bc-raised)", border: "1px solid var(--bc-line-hi)",
        borderRadius: 10, padding: "10px 14px", boxShadow: "0 6px 24px rgba(0,0,0,0.45)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--bc-green)" strokeWidth="2.6"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ flexShrink: 0 }}><path d="M5 12l5 5L20 7" /></svg>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 800 }}>{copy.title}</div>
          {copy.body && <div style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.86em)", marginTop: 2 }}>{copy.body}</div>}
        </div>
      </div>
    );
  }

  return (
    <Sheet label={copy.title} onClose={close} zIndex={998} initialFocus="button" style={{
      padding: "22px 20px calc(20px + var(--bottom-nav-h))", textAlign: "center" }}>
        <div aria-hidden="true" style={{ width: 52, height: 52, borderRadius: "50%", margin: "0 auto 12px",
          background: "var(--bc-raised)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--bc-green)" strokeWidth="2.6"
            strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5L20 7" /></svg>
        </div>
        <div style={{ fontWeight: 900, fontSize: "1.4em", textTransform: "uppercase", fontStretch: "110%" }}>{copy.title}</div>
        {copy.body && <p style={{ color: "var(--bc-muted)", lineHeight: 1.5, margin: "8px 0 18px" }}>{copy.body}</p>}
        <button onClick={close} style={{
          width: "100%", minHeight: 52, background: "var(--bc-yellow)", color: "#081f14", border: "none",
          borderRadius: 10, fontWeight: 900, fontSize: "1em", textTransform: "uppercase", letterSpacing: "0.05em",
          cursor: "pointer", fontFamily: "inherit",
        }}>Done</button>
    </Sheet>
  );
}
