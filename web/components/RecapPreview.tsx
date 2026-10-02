"use client";

/**
 * Sunday recap preview: fetch the card, SHOW it, then offer explicit
 * Share / Copy image / Download. The old button jumped straight to a
 * share sheet or a new tab — on desktop that meant a blocked pop-up or a
 * plain-text 404 page, so it looked like nothing happened. When no recap
 * exists yet (nothing settled), it says so instead.
 */
import { useEffect, useState } from "react";

type State =
  | { kind: "loading" }
  | { kind: "ready"; url: string; blob: Blob }
  | { kind: "none"; reason: string };

const btn = (primary: boolean): React.CSSProperties => ({
  cursor: "pointer", fontFamily: "inherit", fontWeight: 900, fontSize: "max(var(--fs-min), 0.74em)",
  textTransform: "uppercase", letterSpacing: "0.05em", borderRadius: 5, padding: "9px 14px",
  background: primary ? "var(--bc-yellow)" : "transparent",
  color: primary ? "#081f14" : "var(--bc-text)",
  border: `1px solid ${primary ? "var(--bc-yellow)" : "var(--bc-line)"}`,
});

export default function RecapPreview({ groupId, groupName, onClose }: {
  groupId: number; groupName: string; onClose: () => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [note, setNote] = useState("");

  useEffect(() => {
    let objectUrl = "";
    fetch(`/api/recap?group_id=${groupId}`).then(async res => {
      if (!res.ok) {
        const text = (await res.text().catch(() => "")).toLowerCase();
        setState({ kind: "none", reason:
          text.includes("no let it ride season") ? "This group doesn't have a Let It Ride season yet — the recap is built from season picks."
          : text.includes("not settled") || text.includes("no settled") || res.status === 404
            ? "No recap yet. It's built once an event your group played is final and its prize money has settled — usually Sunday night."
            : `The recap couldn't load (${res.status}). Try again in a minute.` });
        return;
      }
      const blob = await res.blob();
      objectUrl = URL.createObjectURL(blob);
      setState({ kind: "ready", url: objectUrl, blob });
    }).catch(() => setState({ kind: "none", reason: "The recap couldn't load. Check your connection and try again." }));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [groupId]);

  const file = state.kind === "ready" ? new File([state.blob], "golf-edge-recap.png", { type: "image/png" }) : null;
  const canShare = !!file && typeof navigator !== "undefined" && typeof navigator.canShare === "function"
    && navigator.canShare({ files: [file] });
  const canCopy = typeof navigator !== "undefined" && !!navigator.clipboard && typeof ClipboardItem !== "undefined";

  async function share() {
    if (!file) return;
    try {
      await navigator.share({ files: [file], text: "Rematch — next week's picks are open:", url: "https://playgolfedge.com/friends" });
    } catch { /* user cancelled */ }
  }
  async function copy() {
    if (state.kind !== "ready") return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": state.blob })]);
      setNote("Copied — paste it into the group chat.");
    } catch { setNote("This browser won't copy images — use Download instead."); }
  }

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 50, background: "rgba(0,0,0,0.6)",
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div onClick={e => e.stopPropagation()} role="dialog" aria-label="Sunday recap" style={{
        background: "var(--bc-card)", border: "1px solid var(--bc-line)", borderRadius: 12,
        padding: 18, width: "min(720px, 100%)", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <span style={{ fontWeight: 900 }}>Sunday recap · {groupName}</span>
          <button onClick={onClose} aria-label="Close" style={{ ...btn(false), padding: "4px 10px" }}>Close</button>
        </div>

        {state.kind === "loading" && <p style={{ color: "var(--bc-muted)" }}>Building the card…</p>}
        {state.kind === "none" && <p style={{ color: "var(--bc-muted)", lineHeight: 1.55, margin: 0 }}>{state.reason}</p>}
        {state.kind === "ready" && (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={state.url} alt={`Sunday recap for ${groupName}`}
              style={{ width: "100%", borderRadius: 8, border: "1px solid var(--bc-line)" }} />
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              {canShare && <button onClick={share} style={btn(true)}>Share</button>}
              {canCopy && <button onClick={copy} style={btn(!canShare)}>Copy image</button>}
              <a href={state.url} download="golf-edge-recap.png" style={{ ...btn(false), textDecoration: "none" }}>Download</a>
            </div>
            {note && <p style={{ color: "var(--bc-green)", fontSize: "0.84em", margin: "10px 0 0" }}>{note}</p>}
          </>
        )}
      </div>
    </div>
  );
}
