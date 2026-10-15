/**
 * Record an inbound reply.
 *
 * The classification and its consequence happen in the CRM, next to the data.
 * Deliberately not here: whatever decides "did this person ask us to stop" has
 * to be the same thing everywhere, and a copy of that logic in the browser
 * would be a second answer to the question that governs whether a person keeps
 * being emailed.
 */
import { NextResponse } from "next/server";
import { recordReplyInCRM } from "../../../../../lib/crm";

export const dynamic = "force-dynamic";

export async function POST(request, { params }) {
  const { id } = await params;
  try {
    const body = await request.json();
    const text = typeof body?.text === "string" ? body.text : "";

    if (!text.trim()) {
      // Refused here rather than passed through. The CRM fails closed on an
      // empty body — it holds the sequence and asks for a human — and
      // generating that state from a mis-click would quietly stall a prospect.
      return NextResponse.json({ ok: false, mode: "invalid", error: "Reply text is required." }, { status: 400 });
    }

    const result = await recordReplyInCRM(id, text);
    return NextResponse.json(result, { status: result.mode === "pending" ? 200 : 201 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message }, { status: 502 });
  }
}
