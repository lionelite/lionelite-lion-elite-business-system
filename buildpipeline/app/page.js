"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

// Prospects come from the CRM, which is the system of record. The three
// hardcoded clinics that used to live here were demo data held in browser
// state: a reload lost everything, and the names were invented, which is
// exactly what must never appear in a list someone might contact.
//
// The page reads through /api/prospects rather than calling the CRM directly,
// because CRM_ADMIN_KEY must stay server-side — a client component talking to
// the CRM would ship the key in the bundle.

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
  const [leads, setLeads] = useState([]);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState("");
  const [form, setForm] = useState({ company: "", contact: "", email: "", city: "", services: "" });
  // "loading" | "live" | "pending" | "error". Reported rather than collapsed
  // into an empty list: an unconfigured CRM and a CRM with no prospects both
  // render as zero rows, and those need different actions from whoever is
  // looking at the screen.
  const [connection, setConnection] = useState({ state: "loading", detail: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/prospects", { cache: "no-store" });
      const body = await response.json();

      if (body.mode === "pending") {
        setConnection({ state: "pending", detail: `Set ${(body.missing || []).join(", ")}` });
        setLeads([]);
        return;
      }
      if (!body.ok) {
        setConnection({ state: "error", detail: body.error || "CRM unreachable" });
        return;
      }

      setLeads(body.prospects);
      setConnection({ state: "live", detail: `${body.prospects.length} prospect(s) from CRM` });
      // Keep the current selection across a reload where possible, so a stage
      // change does not bounce the detail pane back to the first row.
      setSelected(prev => body.prospects.find(p => p.id === prev?.id) || body.prospects[0] || null);
    } catch (error) {
      setConnection({ state: "error", detail: error.message });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => { setDraft(selected ? outreachFor(selected) : ""); }, [selected]);

  const metrics = useMemo(() => ({
    total: leads.length,
    qualified: leads.filter(l => l.score >= 75).length,
    contacted: leads.filter(l => ["Contacted","Replied","Follow-Up","Call Booked","Proposal","Won"].includes(l.stage)).length,
    meetings: leads.filter(l => l.stage === "Call Booked").length
  }), [leads]);

  async function addLead(e) {
    e.preventDefault();
    if (!form.company.trim() || busy) return;
    setBusy(true);
    try {
      // Persisted through the CRM rather than pushed into local state, so it
      // survives a reload and is visible to everything else reading the CRM.
      const response = await fetch("/api/prospects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          company_name: form.company,
          contact_name: form.contact,
          email: form.email,
          city: form.city,
          category: form.services || "clinic"
        })
      });
      const body = await response.json();
      if (body.mode === "pending") {
        setConnection({ state: "pending", detail: `Not saved. Set ${(body.missing || []).join(", ")}` });
      } else if (!body.ok) {
        setConnection({ state: "error", detail: body.error || body.message || "Save failed" });
      } else {
        setForm({ company: "", contact: "", email: "", city: "", services: "" });
        await load();
      }
    } catch (error) {
      setConnection({ state: "error", detail: error.message });
    } finally {
      setBusy(false);
    }
  }

  function updateStage(stage) {
    if (!selected) return;
    setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, stage } : l));
    setSelected(prev => ({ ...prev, stage }));
  }

  function qualify() {
    if (!selected) return;
    const score = scoreLead(selected);
    const stage = score >= 75 ? "Qualified" : "New";
    setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, score, stage } : l));
    setSelected(prev => ({ ...prev, score, stage }));
  }

  function generate() {
    if (!selected) return;
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
          <button className="primary" onClick={() => document.getElementById("add-lead")?.scrollIntoView({ behavior: "smooth" })}>+ Add Prospect</button>
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
            {/* Nothing is selected when the CRM returned no prospects, which is
                the normal state on a fresh workspace. The empty state says why
                rather than rendering a blank card — and crucially, reading
                `selected.company` here would throw and take the whole page
                down, since this is a client component. */}
            {selected ? (
              <>
                <h2>{selected.company}</h2>
                <p className="muted">{[selected.city, selected.services].filter(Boolean).join(" · ")}</p>
                <div className="scoreBlock"><span>ICP Score</span><strong>{selected.score}/100</strong></div>
                <button onClick={qualify}>Re-score Prospect</button>
                <label>Pipeline Stage</label>
                <select value={selected.stage} onChange={e => updateStage(e.target.value)}>
                  {stages.map(s => <option key={s}>{s}</option>)}
                </select>
                <button className="primary full" onClick={generate}>Generate Personalized Outreach</button>
              </>
            ) : (
              <p className="muted">
                {connection.state === "pending"
                  ? `CRM not connected. ${connection.detail}`
                  : connection.state === "error"
                    ? `CRM error: ${connection.detail}`
                    : connection.state === "loading"
                      ? "Loading prospects from the CRM…"
                      : "No prospects yet. Add one, or run a harvest."}
              </p>
            )}
          </aside>
        </div>

        <div className="grid lower">
          <section className="card">
            <div className="cardHead"><div><h2>SDR Message Studio</h2><p>Personalized first-touch messaging for the selected prospect.</p></div></div>
            <textarea value={draft} onChange={e => setDraft(e.target.value)} />
            <div className="actions">
              <button onClick={() => navigator.clipboard?.writeText(draft)}>Copy</button>
              <button onClick={() => updateStage("Contacted")}>Mark Sent</button>
              <button onClick={() => updateStage("Call Booked")}>Mark Call Booked</button>
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
