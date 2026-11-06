import { NextResponse } from "next/server";
import { pushCRMEvent } from "../../../lib/crm";
import { crmConfigurationStatus } from "../../../lib/crm-status.mjs";

export const dynamic = "force-dynamic";

// Safe deployment diagnostic: no CRM requests, records, URLs or secret values.
export async function GET() {
  return NextResponse.json(crmConfigurationStatus(), {
    headers: { "Cache-Control": "no-store" }
  });
}

export async function POST(req) {
  try {
    const body = await req.json();
    const eventType = body?.event_type || "lead.upsert";
    const payload = body?.payload || body;
    const result = await pushCRMEvent(eventType, payload);
    return NextResponse.json(result, { status: result.ok ? 200 : 202 });
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }
}
