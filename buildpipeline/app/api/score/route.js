/**
 * Score a prospect against the campaign's ICP, server-side.
 *
 * The page used to score in the browser with its own function, which made three
 * scorers disagreeing about the same prospect: the CRM's legacy
 * calculate_score, the campaign ICP, and a client-side one that started every
 * prospect at a 45-point baseline so almost everything cleared the bar.
 *
 * Scoring belongs with the criteria. In the browser it cannot be audited, it
 * cannot be tuned from conversion data, and it silently differs per deployment.
 */
import { NextResponse } from "next/server";
import { CRM_CONFIG, crmReadiness, toCrmLead } from "../../../lib/crm";

export const dynamic = "force-dynamic";

export async function POST(request) {
  const readiness = crmReadiness(CRM_CONFIG);
  if (!readiness.ready) {
    return NextResponse.json({ ok: false, mode: "pending", missing: readiness.missing }, { status: 200 });
  }

  const campaignId = process.env.CRM_CAMPAIGN_ID;
  if (!campaignId) {
    // Reported rather than falling back to a local guess: a quietly different
    // score is worse than no score, because it looks authoritative.
    return NextResponse.json(
      { ok: false, mode: "pending", missing: ["CRM_CAMPAIGN_ID"] },
      { status: 200 }
    );
  }

  try {
    const prospect = await request.json();
    const lead = toCrmLead(prospect, CRM_CONFIG.organizationId);

    const response = await fetch(
      `${CRM_CONFIG.apiBase.replace(/\/$/, "")}/campaigns/${campaignId}/score?organization_id=${CRM_CONFIG.organizationId}`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "x-lei-admin-key": CRM_CONFIG.apiKey },
        body: JSON.stringify(lead),
        cache: "no-store"
      }
    );

    const text = await response.text();
    if (!response.ok) throw new Error(`Scoring failed (${response.status}): ${text.slice(0, 300)}`);

    return NextResponse.json({ ok: true, mode: "live", ...JSON.parse(text) }, { status: 200 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message }, { status: 502 });
  }
}
