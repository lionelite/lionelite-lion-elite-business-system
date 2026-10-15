/**
 * Campaigns — read the ICP, and edit it.
 *
 * Server-side so the admin key stays in this process. The PATCH matters as much
 * as the GET: the point of ICP-as-data is that an operator can retune fit
 * without a deploy, and that is only true if something exposes the edit.
 */
import { NextResponse } from "next/server";
import { CRM_CONFIG, crmReadiness } from "../../../lib/crm";

export const dynamic = "force-dynamic";

function crmUrl(path) {
  const base = CRM_CONFIG.apiBase.replace(/\/$/, "");
  const join = path.includes("?") ? "&" : "?";
  return `${base}${path}${join}organization_id=${CRM_CONFIG.organizationId}`;
}

export async function GET() {
  const readiness = crmReadiness(CRM_CONFIG);
  if (!readiness.ready) {
    return NextResponse.json({ ok: false, mode: "pending", missing: readiness.missing, campaigns: [] });
  }

  try {
    const response = await fetch(crmUrl("/campaigns"), {
      headers: { "x-lei-admin-key": CRM_CONFIG.apiKey },
      cache: "no-store"
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`Campaigns read failed (${response.status}): ${text.slice(0, 200)}`);
    return NextResponse.json({ ok: true, mode: "live", campaigns: text ? JSON.parse(text) : [] });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message, campaigns: [] }, { status: 502 });
  }
}

export async function PATCH(request) {
  const readiness = crmReadiness(CRM_CONFIG);
  if (!readiness.ready) {
    return NextResponse.json({ ok: false, mode: "pending", missing: readiness.missing }, { status: 200 });
  }

  try {
    const { id, ...changes } = await request.json();
    if (!id) return NextResponse.json({ ok: false, error: "campaign id is required" }, { status: 400 });

    // Sent as-is. The CRM merges an `icp` patch rather than replacing it, so a
    // single-field edit here cannot drop the exclusion list — doing that merge
    // in two places would be two chances for them to disagree.
    const response = await fetch(crmUrl(`/campaigns/${id}`), {
      method: "PATCH",
      headers: { "content-type": "application/json", "x-lei-admin-key": CRM_CONFIG.apiKey },
      body: JSON.stringify(changes),
      cache: "no-store"
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`Campaign update failed (${response.status}): ${text.slice(0, 200)}`);
    return NextResponse.json({ ok: true, mode: "live", campaign: JSON.parse(text) });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message }, { status: 502 });
  }
}
