"use client";

/**
 * /join/[token] — the one-tap invite page (docs/MOBILE_FIRST_DESIGN.md, flow 1).
 * ==============================================================================
 * Public: a friend opens the texted link before they have an account.
 * Signed out → who invited them + the group, and one button to sign up
 * (Clerk returns them here). Signed in → one button to join. Phone-first:
 * one column, big tap targets, no stats.
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

type Preview = { group_name: string; inviter: string; status: string; message: string; group_id?: number };

const page: React.CSSProperties = {
  minHeight: "70vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px 16px",
};
const card: React.CSSProperties = {
  width: "100%", maxWidth: 420, background: "var(--bc-card)", border: "1px solid var(--bc-line)",
  borderRadius: 14, padding: "28px 22px", textAlign: "center",
};
const button: React.CSSProperties = {
  display: "block", width: "100%", minHeight: 52, marginTop: 22, borderRadius: 12, border: "none",
  background: "var(--bc-yellow-fill)", color: "#0c2a1c", fontWeight: 800, fontSize: "1.05rem", cursor: "pointer",
};

export default function JoinPage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { isLoaded, isSignedIn } = useAuth();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    fetch(`/api/join/${token}`, { cache: "no-store" })
      .then(async r => {
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || "This invite link doesn't work.");
        setPreview(d);
      })
      .catch(e => setError(String(e.message || e)));
  }, [token, isLoaded, isSignedIn]);

  async function join() {
    setJoining(true);
    const r = await fetch(`/api/join/${token}`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (d.joined) {
      router.push(`/friends?group=${d.joined}&joined=1`);
      return;
    }
    setJoining(false);
    setPreview(p => p ? { ...p, status: d.status ?? p.status, message: d.message ?? d.error ?? p.message } : p);
  }

  const here = `/join/${token}`;

  return (
    <div style={page}>
      <div style={card}>
        {error && <p style={{ color: "var(--bc-text)", fontSize: "1.05rem" }}>{error}</p>}
        {!error && !preview && <p style={{ color: "var(--bc-muted)" }}>Opening your invite…</p>}
        {preview && (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/badge.png" alt="Golf Edge" width={88} height={88} style={{ display: "block", margin: "0 auto 14px" }} />
            <div style={{ color: "var(--bc-muted)", fontSize: "0.95rem" }}>{preview.inviter} invited you to</div>
            <h1 style={{ color: "var(--bc-text)", fontSize: "1.6rem", margin: "6px 0 14px", lineHeight: 1.2 }}>
              {preview.group_name}
            </h1>
            <p style={{ color: "var(--bc-text)", fontSize: "1rem", lineHeight: 1.45, margin: 0 }}>{preview.message}</p>

            {preview.status === "ok" && !isSignedIn && (
              <>
                <a href={`/sign-up?redirect_url=${encodeURIComponent(here)}`} style={{ ...button, lineHeight: "52px", textDecoration: "none" }}>
                  Sign up to join
                </a>
                <a href={`/sign-in?redirect_url=${encodeURIComponent(here)}`}
                   style={{ display: "block", marginTop: 14, color: "var(--bc-muted)", fontSize: "0.95rem" }}>
                  Already have an account? Sign in
                </a>
              </>
            )}
            {preview.status === "ok" && isSignedIn && (
              <button style={{ ...button, opacity: joining ? 0.6 : 1 }} disabled={joining} onClick={join}>
                {joining ? "Joining…" : `Join ${preview.group_name}`}
              </button>
            )}
            {preview.status === "already_member" && preview.group_id && (
              <button style={button} onClick={() => router.push(`/friends?group=${preview.group_id}`)}>
                Go to {preview.group_name}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
