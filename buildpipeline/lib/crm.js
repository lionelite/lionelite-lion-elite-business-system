/**
 * CRM adapter — BuildPipeline → Lion Elite Intelligence.
 *
 * The CRM (LION_ELITE_INTELLIGENCE, FastAPI + Postgres on Render) is the system
 * of record. BuildPipeline sources and qualifies, then hands records over. This
 * module is the only place that knows how to talk to it.
 *
 * Three things the first version got wrong, each of which failed silently:
 *
 * 1. It sent `Authorization: Bearer`. The CRM authenticates with an
 *    `X-LEI-Admin-Key` header (app/security.py `require_admin_key`), so a
 *    Bearer token is simply ignored.
 * 2. It posted one lead to `POST /leads`, which returns 409 on a duplicate.
 *    A sync sees the same prospect repeatedly, and the second sighting usually
 *    carries more information than the first — so 409 makes the sync unable to
 *    re-run, and one transient failure becomes a permanent gap. It now posts
 *    batches to `POST /ingest/leads`, which upserts idempotently.
 * 3. It spread BuildPipeline's field names straight into the body. The CRM's
 *    Lead model uses different names (`public_email`, `public_phone`,
 *    `owner_name`, `category`), so most fields never arrived.
 *
 * `workspace` was also a slug string; the CRM scopes rows by numeric
 * `organization_id`, so the id is what gets sent.
 */

export const CRM_CONFIG = {
  apiBase: process.env.CRM_API_BASE || "",
  apiKey: process.env.CRM_ADMIN_KEY || "",
  // Numeric organization id of the workspace these prospects belong to. The CRM
  // rejects a batch naming an unknown organization rather than writing rows
  // that belong to nobody.
  organizationId: process.env.CRM_ORGANIZATION_ID || ""
};

export function crmReadiness(config = CRM_CONFIG) {
  const missing = [];
  if (!config.apiBase) missing.push("CRM_API_BASE");
  if (!config.apiKey) missing.push("CRM_ADMIN_KEY");
  if (!config.organizationId) missing.push("CRM_ORGANIZATION_ID");
  return { ready: missing.length === 0, missing };
}

/**
 * Translate a BuildPipeline prospect into the CRM's Lead vocabulary.
 *
 * Translation happens here, on the BuildPipeline side, so the CRM's field names
 * stay canonical. If both ends translated, neither would be authoritative.
 *
 * Empty values are dropped rather than sent as null: the CRM fills only the
 * fields it is missing, and an explicit null is how a researched phone number
 * gets overwritten with nothing.
 */
export function toCrmLead(prospect = {}, organizationId) {
  const candidate = {
    organization_id: Number(organizationId),
    external_id: prospect.id ?? prospect.external_id ?? null,
    company_name: prospect.company_name ?? prospect.companyName ?? prospect.name,
    category: prospect.category ?? prospect.industry ?? "clinic",
    owner_name: prospect.contact_name ?? prospect.contactName ?? prospect.owner_name,
    public_email: prospect.email ?? prospect.public_email,
    public_phone: prospect.phone ?? prospect.public_phone,
    website: prospect.website ?? prospect.domain,
    city: prospect.city,
    state: prospect.state,
    linkedin_url: prospect.linkedin_url ?? prospect.linkedinUrl,
    instagram_url: prospect.instagram_url ?? prospect.instagramUrl,
    source_url: prospect.source_url ?? prospect.sourceUrl,
    partnership_angle: prospect.partnership_angle ?? prospect.qualification_reason,
    notes: prospect.notes
  };

  const lead = {};
  for (const [key, value] of Object.entries(candidate)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && !value.trim()) continue;
    lead[key] = typeof value === "string" ? value.trim() : value;
  }
  return lead;
}

/**
 * Push prospects to the CRM. Idempotent — safe to re-run on the same batch.
 *
 * Returns `{ ok: false, mode: "pending" }` rather than throwing when the CRM is
 * unconfigured, so a deployment without credentials degrades to a no-op instead
 * of erroring on every sync. A missing credential is a deployment state, not a
 * bug — but it is reported, with the variable names, rather than passed over.
 */
export async function syncProspectsToCRM(prospects, config = CRM_CONFIG, fetchImpl = fetch) {
  const list = Array.isArray(prospects) ? prospects : [prospects];
  const readiness = crmReadiness(config);

  if (!readiness.ready) {
    return {
      ok: false,
      mode: "pending",
      missing: readiness.missing,
      message: `CRM sync not configured. Set: ${readiness.missing.join(", ")}`
    };
  }

  const leads = list.map((prospect) => toCrmLead(prospect, config.organizationId));
  const invalid = leads.filter((lead) => !lead.company_name);
  if (invalid.length) {
    return { ok: false, mode: "invalid", message: `${invalid.length} prospect(s) have no company_name.` };
  }

  const response = await fetchImpl(`${config.apiBase.replace(/\/$/, "")}/ingest/leads`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      // The CRM's own scheme. Not a Bearer token.
      "x-lei-admin-key": config.apiKey
    },
    body: JSON.stringify(leads)
  });

  const text = await response.text();
  if (!response.ok) {
    // Surface the CRM's own message: an unknown organization and an auth
    // failure need different fixes, and a bare status code hides which it was.
    throw new Error(`CRM sync failed (${response.status}): ${text.slice(0, 300)}`);
  }

  return { ok: true, mode: "synced", data: text ? JSON.parse(text) : null };
}

/** Back-compat: the original single-lead entry point. */
export async function pushLeadToCRM(lead, config = CRM_CONFIG, fetchImpl = fetch) {
  return syncProspectsToCRM([lead], config, fetchImpl);
}
