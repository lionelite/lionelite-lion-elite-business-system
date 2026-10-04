import { NextResponse } from "next/server";
import { pushLeadToCRM } from "../../../lib/crm";

export async function POST(req) {
  try {
    const lead = await req.json();
    const result = await pushLeadToCRM(lead);
    return NextResponse.json(result, { status: result.ok ? 200 : 202 });
  } catch (error) {
    return NextResponse.json({ok:false,error:error.message},{status:500});
  }
}
