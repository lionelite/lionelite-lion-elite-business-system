export const CRM_CONFIG = {
  workspace: "lion-elite-clinical",
  apiBase: process.env.CRM_API_BASE || "",
  apiKey: process.env.CRM_API_KEY || ""
};

export async function pushLeadToCRM(lead) {
  if (!CRM_CONFIG.apiBase) return { ok:false, mode:"pending", message:"CRM endpoint not configured yet." };
  const res = await fetch(`${CRM_CONFIG.apiBase.replace(/\/$/,"")}/leads`, {
    method:"POST",
    headers:{"content-type":"application/json","authorization":`Bearer ${CRM_CONFIG.apiKey}`},
    body:JSON.stringify({workspace:CRM_CONFIG.workspace, source:"buildpipeline", ...lead})
  });
  if (!res.ok) throw new Error(`CRM sync failed: ${res.status}`);
  return {ok:true,data:await res.json()};
}
