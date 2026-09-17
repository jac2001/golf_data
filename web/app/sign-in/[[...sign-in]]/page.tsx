/**
 * Sign-in — Clerk's drop-in component centered on the Broadcast green.
 * The [[...sign-in]] folder name is a catch-all route: Clerk uses the
 * extra path segments for its own multi-step flows (verify, SSO, etc.).
 */

import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
      <SignIn />
    </div>
  );
}
