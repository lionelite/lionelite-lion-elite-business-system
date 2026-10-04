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

/**
 * Read prospects back out of the CRM.
 *
 * The CRM is the system of record, so the UI reads from it rather than holding
 * its own copy. These run server-side only — `CRM_ADMIN_KEY` must never reach
 * the browser, which is why `app/api/*` route handlers call these and the page
 * calls the route handlers.
 */
export async function fetchProspectsFromCRM(options = {}, config = CRM_CONFIG, fetchImpl = fetch) {
  const readiness = crmReadiness(config);
  if (!readiness.ready) {
    return { ok: false, mode: "pending", missing: readiness.missing, prospects: [] };
  }

  const params = new URLSearchParams({ organization_id: String(config.organizationId) });
  if (options.limit) params.set("limit", String(options.limit));
  if (options.minScore) params.set("min_score", String(options.minScore));
  if (options.status) params.set("status", options.status);
  if (options.q) params.set("q", options.q);

  const response = await fetchImpl(`${config.apiBase.replace(/\/$/, "")}/leads?${params}`, {
    headers: { "x-lei-admin-key": config.apiKey },
    // The CRM is the source of truth; a cached list would show a stage that has
    // already moved, which is worse than a slower page.
    cache: "no-store"
  });

  const text = await response.text();
  if (!response.ok) throw new Error(`CRM read failed (${response.status}): ${text.slice(0, 300)}`);

  return { ok: true, mode: "live", prospects: (text ? JSON.parse(text) : []).map(fromCrmLead) };
}

export async function fetchStatsFromCRM(config = CRM_CONFIG, fetchImpl = fetch) {
  const readiness = crmReadiness(config);
  if (!readiness.ready) return { ok: false, mode: "pending", missing: readiness.missing, stats: null };

  const params = new URLSearchParams({ organization_id: String(config.organizationId) });
  const response = await fetchImpl(`${config.apiBase.replace(/\/$/, "")}/stats?${params}`, {
    headers: { "x-lei-admin-key": config.apiKey },
    cache: "no-store"
  });

  const text = await response.text();
  if (!response.ok) throw new Error(`CRM stats failed (${response.status}): ${text.slice(0, 300)}`);
  return { ok: true, mode: "live", stats: text ? JSON.parse(text) : null };
}

/**
 * CRM Lead → the shape the UI renders.
 *
 * The inverse of `toCrmLead`. Kept adjacent to it deliberately: when one side
 * gains a field and the other does not, the bug is a value that silently stops
 * appearing, and the two functions being next to each other is what makes that
 * visible in review.
 *
 * `stage` comes from the CRM's lowercase `status` and is mapped to the UI's
 * display labels. An unrecognised status is passed through rather than defaulted
 * to "New" — showing a stage the CRM does not have would misreport the pipeline.
 */
const STAGE_LABELS = {
  new: "New",
  qualified: "Qualified",
  outreach_ready: "Outreach Ready",
  contacted: "Contacted",
  replied: "Replied",
  follow_up: "Follow-Up",
  call_booked: "Call Booked",
  proposal: "Proposal",
  won: "Won",
  lost: "Lost",
  do_not_contact: "Do Not Contact"
};

export function fromCrmLead(lead = {}) {
  return {
    id: lead.id,
    company: lead.company_name || "",
    contact: lead.owner_name || "",
    email: lead.public_email || "",
    phone: lead.public_phone || "",
    website: lead.website || "",
    city: lead.city || "",
    state: lead.state || "",
    services: lead.category || "",
    score: typeof lead.score === "number" ? lead.score : 0,
    stage: STAGE_LABELS[lead.status] || lead.status || "New",
    doNotContact: Boolean(lead.do_not_contact),
    notes: lead.notes || "",
    last: lead.updated_at || "",
    source: lead.source_system || "manual"
  };
}
