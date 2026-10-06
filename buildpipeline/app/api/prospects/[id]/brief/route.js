/** Pre-contact brief: why this prospect fits, what they last said, what to do next. */
import { NextResponse } from "next/server";
import { fetchBriefFromCRM } from "../../../../../lib/crm";

export const dynamic = "force-dynamic";

export async function GET(request, { params }) {
  const { id } = await params;
  try {
    return NextResponse.json(await fetchBriefFromCRM(id), { status: 200 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message }, { status: 502 });
  }
}
