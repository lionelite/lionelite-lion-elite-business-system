/**
 * Prospects — read and create, backed by the CRM.
 *
 * A Next.js route handler, so this runs on the server. That is the whole point:
 * `CRM_ADMIN_KEY` lives in this process and never reaches the browser. The page
 * is a client component and must call this route rather than the CRM directly,
 * or the key would ship in the bundle.
 */
import { NextResponse } from "next/server";
import { fetchProspectsFromCRM, syncProspectsToCRM } from "../../../lib/crm";

// The CRM is the source of truth and a stage can move at any time, so a cached
// response would show state that is already wrong.
export const dynamic = "force-dynamic";

export async function GET(request) {
  const params = request.nextUrl.searchParams;
  try {
    const result = await fetchProspectsFromCRM({
      limit: params.get("limit") || 200,
      status: params.get("status") || undefined,
      q: params.get("q") || undefined
    });

    // Unconfigured is reported as a 200 with `mode: "pending"` rather than an
    // error: the UI needs to render and say what is missing, and a 500 would
    // make a deployment-state problem look like a broken page.
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message, prospects: [] }, { status: 502 });
  }
}

export async function POST(request) {
  try {
    const body = await request.json();
    const prospects = Array.isArray(body) ? body : [body];

    if (!prospects.length) {
      return NextResponse.json({ ok: false, error: "No prospects supplied." }, { status: 400 });
    }

    const result = await syncProspectsToCRM(prospects);
    // 202 when the CRM is not wired up yet: the request was understood, nothing
    // was persisted, and the response says which variables are missing.
    return NextResponse.json(result, { status: result.ok ? 201 : 202 });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 502 });
  }
}
