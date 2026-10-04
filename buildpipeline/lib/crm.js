export const CRM_CONFIG = {
  workspace: "lion-elite-clinical",
  syncUrl: process.env.CRM_SYNC_URL || "",
  apiBase: process.env.CRM_API_BASE || "",
  apiKey: process.env.CRM_API_KEY || ""
};

function endpointFor(eventType) {
  if (CRM_CONFIG.syncUrl) return CRM_CONFIG.syncUrl;
  if (!CRM_CONFIG.apiBase) return "";
  const base = CRM_CONFIG.apiBase.replace(/\/$/, "");
  if (eventType === "lead.upsert") return `${base}/leads`;
  if (eventType === "activity.create") return `${base}/activities`;
  if (eventType === "meeting.upsert") return `${base}/meetings`;
  if (eventType === "deal.upsert") return `${base}/deals`;
  return `${base}/events`;
}

export async function pushCRMEvent(eventType, payload) {
  const endpoint = endpointFor(eventType);
  if (!endpoint) {
    return { ok: false, mode: "pending", message: "CRM sync endpoint is not configured yet." };
  }

  const headers = { "content-type": "application/json" };
  if (CRM_CONFIG.apiKey) headers.authorization = `Bearer ${CRM_CONFIG.apiKey}`;

  const res = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify({
      event_type: eventType,
      workspace: CRM_CONFIG.workspace,
      source: "buildpipeline",
      occurred_at: new Date().toISOString(),
      payload
    }),
    cache: "no-store"
  });

  const body = await res.text();
  let data = body;
  try { data = body ? JSON.parse(body) : null; } catch {}

  if (!res.ok) {
    throw new Error(`CRM sync failed: ${res.status} ${typeof data === "string" ? data : JSON.stringify(data)}`);
  }
  return { ok: true, data };
}

export async function pushLeadToCRM(lead) {
  return pushCRMEvent("lead.upsert", lead);
}
