/**
 * Persist a change to one prospect.
 *
 * This route did not exist, so the page's stage dropdown and its scoring button
 * only changed React state. The pipeline looked editable and forgot everything
 * on reload — which for the one number that matters here ("call booked") means
 * the system could not count the thing it exists to produce.
 */
import { NextResponse } from "next/server";
import { updateProspectInCRM } from "../../../../lib/crm";

export const dynamic = "force-dynamic";

export async function PATCH(request, { params }) {
  const { id } = await params;
  try {
    const changes = await request.json();
    const result = await updateProspectInCRM(id, changes);

    if (result.mode === "pending") return NextResponse.json(result, { status: 200 });
    if (result.mode === "invalid") return NextResponse.json(result, { status: 400 });
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message }, { status: 502 });
  }
}
