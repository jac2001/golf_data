/**
 * The link preview (iMessage, Slack, X...): mascot, name, what it is.
 * Built at build time from assets/brand/mascot.png (cut from Jack's brand sheet).
 */
import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const alt = "Golf Edge: pick golfers, beat your friends";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  const mascot = await readFile(join(process.cwd(), "assets/brand/mascot.png"));
  const src = `data:image/png;base64,${mascot.toString("base64")}`;
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center",
        background: "#06180e", color: "#f2f7f0", fontFamily: "sans-serif", padding: "0 64px 0 24px" }}>
        {/* eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text */}
        <img src={src} width={600} height={426} />
        <div style={{ display: "flex", flexDirection: "column", marginLeft: 24 }}>
          <div style={{ display: "flex", fontSize: 88, fontWeight: 900, letterSpacing: 2, lineHeight: 1 }}>
            GOLF <span style={{ color: "#ffd24a", marginLeft: 22 }}>EDGE</span>
          </div>
          <div style={{ display: "flex", fontSize: 40, fontWeight: 800, marginTop: 22 }}>Pick golfers.</div>
          <div style={{ display: "flex", fontSize: 40, fontWeight: 800, color: "#6fd49a" }}>Beat your friends.</div>
          <div style={{ display: "flex", fontSize: 26, color: "#9dbfa9", marginTop: 26 }}>Free fantasy golf for your group</div>
          <div style={{ display: "flex", fontSize: 26, color: "#ffd24a", marginTop: 6 }}>playgolfedge.com</div>
        </div>
      </div>
    ),
    size,
  );
}
