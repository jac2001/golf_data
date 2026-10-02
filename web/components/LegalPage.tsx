/**
 * LegalPage — shared shell for /terms and /privacy.
 * Plain reading layout: one column, section headings, the effective date
 * up top. Content stays in each page so the wording is easy to review.
 */

import React from "react";
import Link from "next/link";
import { PageHead } from "@/components/broadcast";

export const CONTACT_EMAIL = "admin@playgolfedge.com";
export const EFFECTIVE = "October 2, 2026";

export function LegalPage({ title, kicker, children }: {
  title: string; kicker: string; children: React.ReactNode;
}) {
  return (
    <div style={{ maxWidth: 760, margin: "0 auto" }}>
      <PageHead kicker={kicker} title={title} />
      <p style={{ color: "var(--bc-muted)", fontSize: "max(var(--fs-min), 0.85em)", margin: "0 0 8px" }}>
        Effective {EFFECTIVE}
      </p>
      {children}
      <p style={{ ...P, color: "var(--bc-muted)", marginTop: 40, fontSize: "max(var(--fs-min), 0.88em)" }}>
        See also: <Link href="/terms">Terms of Service</Link> · <Link href="/privacy">Privacy Policy</Link>
      </p>
    </div>
  );
}

const P: React.CSSProperties = {
  color: "var(--bc-text)", lineHeight: 1.7, margin: "12px 0", fontSize: "0.98em",
};

export function H({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      color: "var(--bc-text)", fontSize: "1.15em", marginTop: 34, marginBottom: 8,
      borderBottom: "1px solid var(--bc-line)", paddingBottom: 6,
    }}>{children}</h2>
  );
}

export function Para({ children }: { children: React.ReactNode }) {
  return <p style={P}>{children}</p>;
}

export function List({ items }: { items: React.ReactNode[] }) {
  return (
    <ul style={{ ...P, paddingLeft: 22 }}>
      {items.map((it, i) => <li key={i} style={{ margin: "6px 0" }}>{it}</li>)}
    </ul>
  );
}
