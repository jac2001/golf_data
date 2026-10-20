"use client";

/**
 * Sheet — the one accessible bottom sheet (review item 10).
 * =========================================================
 * A modal dialog done properly: aria-modal + a label, focus moves in on
 * open (the first focusable control, or the sheet itself), Tab and
 * Shift+Tab stay inside, Escape closes, a tap on the backdrop closes, and
 * focus returns to whatever opened it. Used by the chirp thread and the
 * pick confirmation; anything new that slides up should use it too.
 */

import React, { useEffect, useRef } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export default function Sheet({ label, onClose, children, style, zIndex = 400, initialFocus }: {
  label: string;
  onClose: () => void;
  children: React.ReactNode;
  /** Extra styles for the panel (padding, max height...). */
  style?: React.CSSProperties;
  zIndex?: number;
  /** CSS selector inside the sheet to focus first (e.g. the main button). */
  initialFocus?: string;
}) {
  const panel = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const el = panel.current;
    const first = (initialFocus && el?.querySelector<HTMLElement>(initialFocus))
      || el?.querySelector<HTMLElement>(FOCUSABLE) || el;
    first?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { e.stopPropagation(); closeRef.current(); return; }
      if (e.key !== "Tab" || !el) return;
      const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(x => x.offsetParent !== null);
      if (!items.length) { e.preventDefault(); return; }
      const [a, z] = [items[0], items[items.length - 1]];
      if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener && document.contains(opener)) opener.focus();   // back to the trigger
    };
  }, [initialFocus]);

  return (
    <>
      <div onClick={() => closeRef.current()} aria-hidden="true"
        style={{ position: "fixed", inset: 0, zIndex, background: "rgba(0,0,0,0.55)" }} />
      <div ref={panel} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} style={{
        position: "fixed", left: 0, right: 0, bottom: 0, zIndex: zIndex + 1, maxWidth: 560, margin: "0 auto",
        background: "var(--bc-panel)", borderTop: "1px solid var(--bc-line-hi)", borderRadius: "16px 16px 0 0",
        outline: "none", ...style,
      }}>
        {children}
      </div>
    </>
  );
}
