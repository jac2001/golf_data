"use client";

/**
 * Term — a "?" beside a label that explains it in plain language.
 * ================================================================
 * Content is Jack's glossary (lib/glossary.ts), or an explicit `help`
 * entry (lib/columnHelp.ts for table columns). Opens on tap, Enter or
 * Space (it's a real button); closes on Escape, an outside tap, or a second
 * tap. Never lets the tap reach its container, so a sortable column header
 * doesn't re-sort when you ask what the column means. An unknown term
 * renders just the label.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getGlossaryEntry } from "@/lib/glossary";
import styles from "./Term.module.css";

type Help = { label: string; definition: string; example: string };

export default function Term({ term, help, children }: { term?: string; help?: Help; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const [shift, setShift] = useState(0);   // px left, so the box never crosses the right edge
  const entry = help ?? getGlossaryEntry(term);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onDown = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [open]);

  // Wider screens: after opening, measure and slide left if the box would
  // cross the viewport's right edge (phones use the fixed sheet instead).
  useLayoutEffect(() => {
    if (!open) { setShift(0); return; }
    const el = pop.current;
    if (!el || getComputedStyle(el).position === "fixed") return;
    const over = el.getBoundingClientRect().right - (window.innerWidth - 8);
    if (over > 0) setShift(over);
  }, [open]);

  if (!entry) return <>{children}</>;
  return (
    <span ref={box} style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 4 }}>
      {children}
      <button
        type="button"
        aria-label={`What is ${entry.label}?`}
        aria-expanded={open}
        onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        onKeyDown={e => e.stopPropagation()}
        style={{
          width: 18, height: 18, borderRadius: "50%", padding: 0, lineHeight: "16px",
          border: "1px solid var(--bc-line-hi)", background: "transparent", color: "var(--bc-text)",
          fontSize: 11, fontWeight: 800, cursor: "pointer", fontFamily: "inherit", flexShrink: 0,
        }}
      >?</button>
      {open && (
        <span
          ref={pop}
          role="dialog"
          aria-label={entry.label}
          className={styles.pop}
          onClick={e => e.stopPropagation()}
          style={shift ? { left: -shift } : undefined}
        >
          <strong style={{ display: "block", marginBottom: 4 }}>{entry.label}</strong>
          {entry.definition}
          <span style={{ display: "block", marginTop: 6, color: "var(--bc-muted)" }}>{entry.example}</span>
        </span>
      )}
    </span>
  );
}
