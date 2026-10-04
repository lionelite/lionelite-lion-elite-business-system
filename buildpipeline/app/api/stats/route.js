/**
 * Funnel metrics for the dashboard, read from the CRM.
 *
 * Server-side for the same reason as the prospects route: the admin key stays
 * in this process.
 */
import { NextResponse } from "next/server";
import { fetchStatsFromCRM } from "../../../lib/crm";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const result = await fetchStatsFromCRM();
    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    return NextResponse.json({ ok: false, mode: "error", error: error.message, stats: null }, { status: 502 });
  }
}
