/** Unprotected diagnostic: proves whether API route functions exist and
 *  are reachable in the production deployment, independent of auth. */
export async function GET() {
  return Response.json({ ok: true, at: new Date().toISOString() });
}
