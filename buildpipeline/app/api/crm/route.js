import { NextResponse } from "next/server";
import { pushCRMEvent } from "../../../lib/crm";

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
