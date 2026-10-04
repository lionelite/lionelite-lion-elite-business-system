"use client";

import { useMemo, useState } from "react";

const initialLeads = [
  { id: 1, company: "Miami Wellness & Weight Loss", contact: "Clinic Owner", email: "", city: "Miami, FL", services: "Weight loss, wellness", score: 92, stage: "Qualified", last: "Not contacted", next: "Generate outreach" },
  { id: 2, company: "South Florida Hormone Center", contact: "Medical Director", email: "", city: "Fort Lauderdale, FL", services: "TRT, hormone optimization", score: 88, stage: "Qualified", last: "Not contacted", next: "Generate outreach" },
  { id: 3, company: "Premier Med Spa", contact: "Practice Manager", email: "", city: "Boca Raton, FL", services: "Med spa, aesthetics", score: 81, stage: "New", last: "Not contacted", next: "Qualify" }
];

const stages = ["New","Qualified","Outreach Ready","Contacted","Replied","Follow-Up","Call Booked","Proposal","Won","Lost"];

function scoreLead(lead) {
  const hay = `${lead.company} ${lead.services} ${lead.city}`.toLowerCase();
  let score = 45;
  if (/clinic|medical|wellness|hormone|med spa|weight|trt|regenerative/.test(hay)) score += 25;
  if (/weight|hormone|trt|wellness|regenerative/.test(hay)) score += 15;
  if (/fl|florida|miami|boca|fort lauderdale/.test(hay)) score += 8;
  if (lead.email) score += 5;
  return Math.min(score, 100);
}

function outreachFor(lead) {
  const angle = /hormone|trt/i.test(lead.services)
    ? "expanding patient offerings and simplifying access to properly documented clinical products"
    : /weight/i.test(lead.services)
      ? "supporting a stronger weight-management offering with reliable clinical fulfillment"
      : "helping clinics expand their treatment offering without adding operational friction";
  return `Subject: Quick idea for ${lead.company}

Hi ${lead.contact || "there"},

I came across ${lead.company} and noticed your focus on ${lead.services || "patient wellness"}. We work with clinics on ${angle}.

I’d like to show you the process, pricing structure, and how we can support your team without creating extra admin work.

Would a quick 10-minute walkthrough this week be worth it?

— Lion Elite Clinical`;
}

export default function Home() {
  const [leads, setLeads] = useState(initialLeads);
  const [selected, setSelected] = useState(initialLeads[0]);
  const [draft, setDraft] = useState(outreachFor(initialLeads[0]));
  const [form, setForm] = useState({ company: "", contact: "", email: "", city: "", services: "" });
  const [syncState, setSyncState] = useState({ status: "idle", message: "CRM bridge ready" });

  async function syncCRM(eventType, payload) {
    setSyncState({ status: "syncing", message: "Syncing with Lion Elite Clinical CRM…" });
    try {
      const res = await fetch("/api/crm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ event_type: eventType, payload })
      });
      const result = await res.json();
      if (result.ok) {
        setSyncState({ status: "synced", message: "Synced with Lion Elite Clinical CRM" });
      } else {
        setSyncState({ status: "pending", message: result.message || "CRM endpoint awaiting final Base44 connection" });
      }
      return result;
    } catch (error) {
      setSyncState({ status: "error", message: error.message || "CRM sync failed" });
      return { ok: false, error: error.message };
    }
  }

  function crmLead(lead) {
    const statusMap = {
      "New": "new",
      "Qualified": "qualified",
      "Outreach Ready": "qualified",
      "Contacted": "contacted",
      "Replied": "responded",
      "Follow-Up": "responded",
      "Call Booked": "meeting_booked",
      "Proposal": "proposal",
      "Won": "client",
      "Lost": "not_interested"
    };
    const [city = "", state = ""] = (lead.city || "").split(",").map(v => v.trim());
    return {
      external_id: String(lead.id),
      clinic_name: lead.company,
      contact_name: lead.contact,
      email: lead.email,
      city,
      state,
      services: lead.services,
      icp_score: lead.score,
      status: statusMap[lead.stage] || "new",
      source: "buildpipeline",
      sync_source: "buildpipeline",
      last_synced_at: new Date().toISOString()
    };
  }

  const metrics = useMemo(() => ({
    total: leads.length,
    qualified: leads.filter(l => l.score >= 75).length,
    contacted: leads.filter(l => ["Contacted","Replied","Follow-Up","Call Booked","Proposal","Won"].includes(l.stage)).length,
    meetings: leads.filter(l => l.stage === "Call Booked").length
  }), [leads]);

  async function addLead(e) {
    e.preventDefault();
    if (!form.company.trim()) return;
    const lead = { id: Date.now(), ...form, score: scoreLead(form), stage: "New", last: "Not contacted", next: "Qualify" };
    setLeads(prev => [lead, ...prev]);
    setSelected(lead);
    setDraft(outreachFor(lead));
    setForm({ company: "", contact: "", email: "", city: "", services: "" });
    await syncCRM("lead.upsert", crmLead(lead));
  }

  async function updateStage(stage) {
    setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, stage } : l));
    const updated = { ...selected, stage };
    setSelected(updated);
    await syncCRM("lead.upsert", crmLead(updated));
    if (stage === "Call Booked") await syncCRM("meeting.upsert", { ...crmLead(updated), status: "scheduled" });
    if (["Proposal","Won","Lost"].includes(stage)) await syncCRM("deal.upsert", { ...crmLead(updated), stage });
  }

  async function qualify() {
    const score = scoreLead(selected);
    const stage = score >= 75 ? "Qualified" : "New";
    setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, score, stage } : l));
    const updated = { ...selected, score, stage };
    setSelected(updated);
    await syncCRM("lead.upsert", crmLead(updated));
  }

  function generate() {
    const nextDraft = outreachFor(selected);
    setDraft(nextDraft);
    if (selected.stage === "Qualified" || selected.stage === "New") updateStage("Outreach Ready");
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <div className="brand">BUILD<span>PIPELINE</span></div>
          <p className="muted">Automated SDR Operating System</p>
        </div>
        <nav>
          <button className="nav active">Pipeline</button>
          <button className="nav">Prospects</button>
          <button className="nav">Outreach</button>
          <button className="nav">Meetings</button>
          <button className="nav">Analytics</button>
        </nav>
        <div className="workspace">
          <small>ACTIVE WORKSPACE</small>
          <strong>Lion Elite Clinical</strong>
          <span>Internal case study</span>
        </div>
      </aside>

      <section className="content">
        <header className="top">
          <div>
            <p className="eyebrow">BUILDPIPELINE / LION ELITE CLINICAL</p>
            <h1>AI SDR Command Center</h1>
            <p className="muted">Prove the acquisition engine internally, then sell the same system to other businesses.</p>
          </div>
          <div>
            <button className="primary" onClick={() => document.getElementById("add-lead")?.scrollIntoView({ behavior: "smooth" })}>+ Add Prospect</button>
            <p className="muted" style={{marginTop:8,textAlign:"right",fontSize:12}}>{syncState.message}</p>
          </div>
        </header>

        <div className="metrics">
          <Metric label="Prospects" value={metrics.total} />
          <Metric label="Qualified" value={metrics.qualified} />
          <Metric label="Contacted" value={metrics.contacted} />
          <Metric label="Calls Booked" value={metrics.meetings} />
        </div>

        <div className="grid">
          <section className="card pipeline">
            <div className="cardHead">
              <div><h2>Clinical Prospect Pipeline</h2><p>Target: wellness, weight loss, TRT, med spa and regenerative clinics</p></div>
            </div>
            <div className="tableWrap">
              <table>
                <thead><tr><th>Company</th><th>Location</th><th>Score</th><th>Stage</th><th>Next Action</th></tr></thead>
                <tbody>
                  {leads.map(lead => (
                    <tr key={lead.id} onClick={() => { setSelected(lead); setDraft(outreachFor(lead)); }} className={selected?.id === lead.id ? "selected" : ""}>
                      <td><strong>{lead.company}</strong><span>{lead.services}</span></td>
                      <td>{lead.city}</td>
                      <td><span className={`score ${lead.score >= 85 ? "hot" : lead.score >= 75 ? "warm" : ""}`}>{lead.score}</span></td>
                      <td>{lead.stage}</td>
                      <td>{lead.next}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="card detail">
            <p className="eyebrow">SELECTED PROSPECT</p>
            <h2>{selected.company}</h2>
            <p className="muted">{selected.city} · {selected.services}</p>
            <div className="scoreBlock"><span>ICP Score</span><strong>{selected.score}/100</strong></div>
            <button onClick={qualify}>Re-score Prospect</button>
            <label>Pipeline Stage</label>
            <select value={selected.stage} onChange={e => updateStage(e.target.value)}>
              {stages.map(s => <option key={s}>{s}</option>)}
            </select>
            <button className="primary full" onClick={generate}>Generate Personalized Outreach</button>
          </aside>
        </div>

        <div className="grid lower">
          <section className="card">
            <div className="cardHead"><div><h2>SDR Message Studio</h2><p>Personalized first-touch messaging for the selected prospect.</p></div></div>
            <textarea value={draft} onChange={e => setDraft(e.target.value)} />
            <div className="actions">
              <button onClick={() => navigator.clipboard?.writeText(draft)}>Copy</button>
              <button onClick={async () => {
                await updateStage("Contacted");
                await syncCRM("activity.create", { ...crmLead({ ...selected, stage: "Contacted" }), channel: "email", direction: "outbound", message: draft, status: "sent" });
              }}>Mark Sent + Sync</button>
              <button onClick={() => updateStage("Call Booked")}>Mark Call Booked + Sync</button>
            </div>
          </section>

          <section className="card" id="add-lead">
            <div className="cardHead"><div><h2>Add Prospect</h2><p>Start with manually sourced prospects, then plug in automated enrichment.</p></div></div>
            <form onSubmit={addLead}>
              <input placeholder="Clinic / business name" value={form.company} onChange={e => setForm({...form, company:e.target.value})} />
              <input placeholder="Decision maker" value={form.contact} onChange={e => setForm({...form, contact:e.target.value})} />
              <input placeholder="Email" value={form.email} onChange={e => setForm({...form, email:e.target.value})} />
              <input placeholder="City, State" value={form.city} onChange={e => setForm({...form, city:e.target.value})} />
              <input placeholder="Services offered" value={form.services} onChange={e => setForm({...form, services:e.target.value})} />
              <button className="primary full" type="submit">Add + Score Prospect</button>
            </form>
          </section>
        </div>

        <section className="card roadmap">
          <p className="eyebrow">AUTOMATION ROADMAP</p>
          <div className="roadGrid">
            <div><b>01</b><strong>Source</strong><span>Find ICP-matched clinics</span></div>
            <div><b>02</b><strong>Qualify</strong><span>Score fit + pain points</span></div>
            <div><b>03</b><strong>Outreach</strong><span>Personalized multi-touch sequences</span></div>
            <div><b>04</b><strong>Book</strong><span>Route positive replies to calendar</span></div>
            <div><b>05</b><strong>Learn</strong><span>Optimize from replies + closed revenue</span></div>
          </div>
        </section>
      </section>
    </main>
  );
}

function Metric({label, value}) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
