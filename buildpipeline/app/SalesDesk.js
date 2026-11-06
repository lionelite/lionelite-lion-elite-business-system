"use client";

import { useState } from "react";
import playbook from "../lib/sales-playbook.json";

const fields = [
  ["baseline", "Current monthly revenue"], ["goal", "Revenue goal and timeframe"],
  ["bottleneck", "Main bottleneck"], ["decision", "Decision maker and approval process"],
  ["objection", "Objection and response"], ["evidence", "Evidence shown / still needed"],
  ["action", "Agreed next action"], ["owner", "Action owner"],
  ["due", "Due date, time and timezone"], ["scope", "Scope, agreement and payment status"]
];

export default function SalesDesk({ leads, selected, onSelect, onSaved, connected }) {
  const [record, setRecord] = useState({});
  const [brand, setBrand] = useState("BuildPipeline");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");
  const suppressed = selected?.doNotContact || selected?.stage === "Do Not Contact";
  const dirty = Object.values(record).some(Boolean);
  async function save(event) {
    event.preventDefault();
    if (!selected || saving || suppressed) return;
    setSaving(true); setMessage("");
    try {
      // Refresh immediately before appending, preserving existing CRM notes.
      const freshResponse = await fetch("/api/prospects", { cache: "no-store" });
      const fresh = await freshResponse.json();
      if (!freshResponse.ok || !fresh.ok) throw new Error("Cannot read current CRM record. Nothing saved.");
      const lead = fresh.prospects.find(item => String(item.id) === String(selected.id));
      if (!lead) throw new Error("Prospect no longer available. Nothing saved.");
      if (lead.doNotContact || lead.stage === "Do Not Contact") throw new Error("This prospect is marked Do Not Contact.");
      const entry = [
        "[Sales call — " + new Date().toISOString() + "]",
        "Offer: " + brand,
        ...fields.map(([key, label]) => label + ": " + (record[key]?.trim() || "Not recorded"))
      ].join("\n");
      const response = await fetch("/api/prospects/" + encodeURIComponent(lead.id), {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ notes: [lead.notes, entry].filter(Boolean).join("\n\n") })
      });
      const result = await response.json();
      if (!response.ok || !result.ok || !result.prospect) throw new Error(result.error || result.message || "CRM did not confirm the save.");
      onSaved(result.prospect); setRecord({}); setMessage("Saved to the prospect’s CRM notes.");
    } catch (error) { setMessage(error.message); }
    finally { setSaving(false); }
  }
  const visible = playbook.filter(item => (item.title + " " + item.body).toLowerCase().includes(query.toLowerCase()));
  return <div className="salesDesk">
    <section className="card offer">
      <p className="eyebrow">CONFIRMED OFFER · BUILDPIPELINE</p>
      <h2>90 days to build a stronger sales operation</h2>
      <p>Business diagnosis, rep coaching, offer development, qualified opportunities and conversion review.</p>
      <div className="metrics">
        <div className="metric"><span>Total engagement</span><strong>$10,000</strong></div>
        <div className="metric"><span>At signing</span><strong>$5,000</strong></div>
        <div className="metric"><span>Day 30</span><strong>$2,500</strong></div>
        <div className="metric"><span>Day 60</span><strong>$2,500</strong></div>
      </div>
      <p>For businesses around $7K–$8K/month pursuing $35K–$50K/month. These are goals, not guaranteed results or a promised 90-day outcome.</p>
      <ol className="delivery"><li><b>Days 1–30:</b> Diagnose the business, offer and sales process.</li><li><b>Days 31–60:</b> Coach reps, generate qualified opportunities and strengthen follow-up.</li><li><b>Days 61–90:</b> Review conversion, improve execution and hand off the operating plan.</li></ol>
      <p className="muted">No automatic renewal. Ad spend and outside software are separate. Confirm coaching cadence, rep count, channels, volume and staffing in the agreement before signing.</p>
    </section>
    <div className="grid">
      <section className="card">
        <p className="eyebrow">CONVERSATION GUIDE</p>
        <h2>Discover → diagnose → offer → resolve → agree</h2>
        <p className="muted">Credibility: Sales 1 reference. Price/value: Sales 2. Resistance to questions: Sales 3. Use evidence you can substantiate and record a specific next step.</p>
        <label htmlFor="script-search">Find a script or objection</label>
        <input id="script-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Try price, discovery, Clinical or Beauty" />
        {visible.map(section => <details key={section.title}><summary>{section.title}</summary><div className="scriptText">{section.body}</div></details>)}
        {!visible.length && <p>No matching scripts.</p>}
      </section>
      <section className="card">
        <p className="eyebrow">CALL WORKSHEET</p>
        <h2>Record the decision and next step</h2>
        <p className="muted">Saved records append to CRM notes. Action dates are recorded for follow-up; they do not create reminders.</p>
        <label htmlFor="sales-prospect">Prospect</label>
        <select id="sales-prospect" value={selected?.id ?? ""} disabled={saving || dirty} onChange={e => { onSelect(leads.find(l => String(l.id) === e.target.value)); setMessage(""); }}>
          <option value="" disabled>Select a prospect</option>
          {leads.map(lead => <option key={lead.id} value={lead.id}>{lead.company}</option>)}
        </select>
        {dirty && <p className="muted">Save or clear this worksheet before changing prospects.</p>}
        {!connected && <p role="status">CRM is not connected. Scripts remain available; saving is disabled.</p>}
        {suppressed && <p role="status">Do not contact. This prospect is suppressed.</p>}
        <form onSubmit={save}>
          <label htmlFor="sales-brand">Offer</label>
          <select id="sales-brand" value={brand} onChange={e => setBrand(e.target.value)} disabled={saving}>
            {["BuildPipeline", "Lion Elite Clinical", "Lion Elite Beauty", "Lion Elite Wellness"].map(name => <option key={name}>{name}</option>)}
          </select>
          {fields.map(([key, label]) => <label key={key} htmlFor={"call-" + key}>{label}{["action","owner","due"].includes(key) ? " *" : ""}
            <input id={"call-" + key} value={record[key] || ""} maxLength={1200} required={["action","owner","due"].includes(key)} disabled={saving} onChange={e => setRecord({...record, [key]: e.target.value})} />
          </label>)}
          <button className="primary" disabled={!selected || !connected || suppressed || saving}>{saving ? "Saving…" : "Save call to CRM"}</button>
          <button type="button" disabled={saving} onClick={() => {setRecord({}); setMessage("");}}>Clear worksheet</button>
        </form>
        <p role="status" aria-live="polite">{message}</p>
        {selected?.notes && <details><summary>Existing CRM notes</summary><div className="scriptText">{selected.notes}</div></details>}
      </section>
    </div>
  </div>;
}
