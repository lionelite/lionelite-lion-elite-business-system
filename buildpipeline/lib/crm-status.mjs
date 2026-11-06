// Reports configuration shape only. Never returns credentials or reads CRM records.
export function crmConfigurationStatus(env = process.env) {
  const keys = ["CRM_API_BASE", "CRM_ADMIN_KEY", "CRM_ORGANIZATION_ID"];
  const missing = keys.filter(key => !String(env[key] || "").trim());
  const invalid = [];
  if (!missing.includes("CRM_API_BASE")) {
    try {
      const url = new URL(env.CRM_API_BASE);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) invalid.push("CRM_API_BASE");
    } catch { invalid.push("CRM_API_BASE"); }
  }
  if (!missing.includes("CRM_ORGANIZATION_ID") &&
      (!/^\d+$/.test(env.CRM_ORGANIZATION_ID) || !Number.isSafeInteger(Number(env.CRM_ORGANIZATION_ID)) || Number(env.CRM_ORGANIZATION_ID) < 1)) {
    invalid.push("CRM_ORGANIZATION_ID");
  }
  return {
    configured: missing.length === 0 && invalid.length === 0,
    missing,
    invalid,
    connectionVerified: false,
    message: "Configuration check only; CRM authentication, availability and saving are not tested."
  };
}
