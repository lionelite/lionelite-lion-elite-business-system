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

// "Do Not Contact" is a terminal stage, not a score. qualify() routes an
// ICP-excluded prospect here rather than back to New, and it was missing from
// this list — so the stage select had no matching option and React would warn
// on a value it could not render.
const stages = ["New","Qualified","Outreach Ready","Contacted","Replied","Follow-Up","Call Booked","Proposal","Won","Lost","Do Not Contact"];

// Scoring moved server-side to /api/score, which evaluates against the
// campaign's editable ICP. The function that was here started every prospect at
// a 45-point baseline and added from there, so almost anything cleared the bar
// — and it was a third opinion, disagreeing with both the CRM's legacy scorer
// and the campaign criteria. Three scorers meant three answers for one
// prospect, and the browser's was the one nobody could audit or tune.

// Outreach copy for a Research-Use-Only supplier.
//
// The previous draft offered "expanding patient offerings", "properly
// documented clinical products" and "treatment offering". That is human-use
// framing — it implies the material is for administration to patients, which is
// exactly the claim an RUO supplier must never make, and it would have gone out
// under the Lion Elite name. The replacement sells what is actually being sold:
// documented, batch-tested research material, for research use.
//
// Deliberately makes no claim about efficacy, treatment or patients, and names
// no compound. A draft is a starting point for a human, so it is written to be
// safe to send unedited rather than relying on someone catching it.
function outreachFor(lead) {
  const angle = /hormone|trt|regenerative|longevity/i.test(lead.services)
    ? "research-grade peptides with batch-specific third-party testing"
    : /weight/i.test(lead.services)
      ? "reliably documented research-grade supply"
      : "research-grade supply with verifiable documentation";

  return `Subject: Research-grade supply documentation for ${lead.company}

Hi ${lead.contact || `${lead.company} team`},

I'm reaching out from Lion Elite Clinical. We supply ${angle} for laboratory research purposes only, with a certificate of analysis for every batch and clear research-use-only labelling on each item.

If ${lead.company} sources research compounds, we'd like to be considered as a supplier. What distinguishes our catalogue is verifiable documentation and consistent fulfilment.

Would you be open to a short call to review the catalogue and the batch testing documentation?

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
  // The nav buttons were decorative — five labels, none of which did anything.
  const [view, setView] = useState("Pipeline");
  const [campaigns, setCampaigns] = useState([]);
  const [brief, setBrief] = useState(null);
  const [replyText, setReplyText] = useState("");
  // What the last save actually did, shown next to the control that did it. A
  // persisted change and a discarded one looked identical before this.
  const [saveNote, setSaveNote] = useState("");

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

  const loadCampaigns = useCallback(async () => {
    try {
      const body = await (await fetch("/api/campaigns", { cache: "no-store" })).json();
      if (body.ok) setCampaigns(body.campaigns);
    } catch {
      // The campaign list is secondary to the prospect list; a failure here
      // must not blank the dashboard, and the connection banner already
      // reports a CRM that is unreachable.
    }
  }, []);

  const loadBrief = useCallback(async (leadId) => {
    if (!leadId) { setBrief(null); return; }
    try {
      const body = await (await fetch(`/api/prospects/${leadId}/brief`, { cache: "no-store" })).json();
      setBrief(body.ok ? body.brief : null);
    } catch {
      // The brief is additive context. Losing it must not break the pane that
      // shows the contact details someone is about to dial.
      setBrief(null);
    }
  }, []);

  useEffect(() => { load(); loadCampaigns(); }, [load, loadCampaigns]);
  useEffect(() => {
    loadBrief(selected?.id);
    setReplyText("");
    setSaveNote("");
  }, [selected?.id, loadBrief]);

  // Editing the qualification threshold is the smallest useful proof that ICP
  // is data rather than code: change it here, and re-scoring answers
  // differently with no deploy.
  async function updateThreshold(campaign, value) {
    const qualified_at = Number(value);
    if (!Number.isFinite(qualified_at) || busy) return;
    setBusy(true);
    try {
      const body = await (await fetch("/api/campaigns", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: campaign.id, icp: { qualified_at } })
      })).json();
      if (body.ok) setCampaigns(prev => prev.map(c => c.id === body.campaign.id ? body.campaign : c));
      else setConnection({ state: "error", detail: body.error || "Could not update the campaign" });
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { setDraft(selected ? outreachFor(selected) : ""); }, [selected]);

  // Counted off the stage, not off a score threshold held here. The old version
  // used `score >= 75`, which was a second copy of the campaign's qualified_at
  // living in the browser — edit the threshold in Campaigns and this number
  // kept answering with the old one. The stage is set by scoring against the
  // campaign, so it already carries the current threshold.
  //
  // And a suppressed contact is excluded from every count. They opted out, so
  // they cannot convert; counting them inflates the only numbers anyone here
  // is judged on.
  const QUALIFIED_STAGES = ["Qualified","Outreach Ready","Contacted","Replied","Follow-Up","Call Booked","Proposal","Won"];
  // One definition, used by the detail pane, the studio and the draft guard.
  // Three separate inline checks is how one of them ends up missing the case.
  const suppressed = Boolean(selected?.doNotContact || selected?.stage === "Do Not Contact");

  const metrics = useMemo(() => {
    const live = leads.filter(l => !l.doNotContact && l.stage !== "Do Not Contact");
    return {
      total: leads.length,
      qualified: live.filter(l => QUALIFIED_STAGES.includes(l.stage)).length,
      contacted: live.filter(l => ["Contacted","Replied","Follow-Up","Call Booked","Proposal","Won"].includes(l.stage)).length,
      meetings: live.filter(l => l.stage === "Call Booked").length
    };
  }, [leads]);

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

  // Writes to the CRM. The previous version set React state only, so moving a
  // prospect to "Call Booked" reverted on the next reload — the pipeline looked
  // editable and remembered nothing, including the one event this product
  // exists to produce.
  async function updateStage(stage) {
    if (!selected || busy) return;
    const previous = selected.stage;

    // Optimistic, then reconciled against what the CRM returns. A dropdown that
    // waits on a round trip feels broken; one that never reconciles lies.
    setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, stage } : l));
    setSelected(prev => ({ ...prev, stage }));
    setBusy(true);
    setSaveNote("Saving…");

    try {
      const body = await (await fetch(`/api/prospects/${selected.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ stage })
      })).json();

      if (!body.ok) {
        // Rolled back, because leaving the new stage on screen would show a
        // change that is not in the system of record.
        setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, stage: previous } : l));
        setSelected(prev => ({ ...prev, stage: previous }));
        setSaveNote(body.mode === "pending"
          ? `Not saved — set ${(body.missing || []).join(", ")}`
          : `Not saved — ${body.error || body.message || "CRM refused the change"}`);
        return;
      }
      setSaveNote(`Saved: ${stage}`);
      if (body.prospect) {
        setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, ...body.prospect } : l));
        setSelected(prev => ({ ...prev, ...body.prospect }));
      }
    } catch (error) {
      setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, stage: previous } : l));
      setSelected(prev => ({ ...prev, stage: previous }));
      setSaveNote(`Not saved — ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  // Record an inbound reply. The CRM classifies it and applies the consequence
  // — suppression on an opt-out, written to the lead — so this reports what
  // happened to the record rather than what it recommended.
  async function logReply() {
    if (!selected || busy || !replyText.trim()) return;
    setBusy(true);
    setSaveNote("Recording reply…");
    try {
      const body = await (await fetch(`/api/prospects/${selected.id}/replies`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: replyText })
      })).json();

      if (!body.ok) {
        setSaveNote(body.mode === "pending"
          ? `Not recorded — set ${(body.missing || []).join(", ")}`
          : `Not recorded — ${body.error || "CRM refused it"}`);
        return;
      }

      const result = body.result || {};
      const intent = result.classification?.intent || "unknown";
      setSaveNote(
        result.suppressed
          ? `Recorded as ${intent}. Contact suppressed — no further sends.`
          : `Recorded as ${intent}. ${result.sequence_stopped ? "Sequence stopped." : "Cadence continues."}`
      );
      setReplyText("");
      await load();
      await loadBrief(selected.id);
    } catch (error) {
      setSaveNote(`Not recorded — ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  // Scores through the campaign rather than locally, and surfaces the reasons.
  // A bare number gives an operator nothing to act on; "category 'trt clinic'
  // +35, no public_phone +0" tells them what is missing.
  async function qualify() {
    if (!selected || busy) return;
    setBusy(true);
    try {
      const response = await fetch("/api/score", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          company_name: selected.company, category: selected.services,
          state: selected.state, city: selected.city,
          email: selected.email, phone: selected.phone,
          contact_name: selected.contact, website: selected.website
        })
      });
      const body = await response.json();

      if (body.mode === "pending") {
        setConnection({ state: "pending", detail: `Scoring needs ${(body.missing || []).join(", ")}` });
        return;
      }
      if (!body.ok) {
        setConnection({ state: "error", detail: body.error || "Scoring failed" });
        return;
      }

      // An excluded prospect is not a low score — it is one this campaign must
      // not contact, so it goes to Do Not Contact rather than back to New.
      const stage = body.excluded ? "Do Not Contact" : body.qualified ? "Qualified" : "New";
      setSelected(prev => ({ ...prev, reasons: body.reasons }));

      // Persisted, not just rendered. A score computed against the campaign ICP
      // and then thrown away means the next person to open this record sees the
      // old number, and the qualified list cannot be filtered on it.
      const saved = await (await fetch(`/api/prospects/${selected.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ stage, score: body.score })
      })).json();

      if (!saved.ok) {
        setSaveNote(saved.mode === "pending"
          ? `Scored ${body.score}, not saved — set ${(saved.missing || []).join(", ")}`
          : `Scored ${body.score}, not saved — ${saved.error || saved.message || "CRM refused it"}`);
        return;
      }

      setLeads(prev => prev.map(l => l.id === selected.id ? { ...l, score: body.score, stage } : l));
      setSelected(prev => ({ ...prev, score: body.score, stage, reasons: body.reasons }));
      setSaveNote(`Scored ${body.score} — ${stage}`);
      await loadBrief(selected.id);
    } catch (error) {
      setConnection({ state: "error", detail: error.message });
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (!selected) return;
    // Refuses on a suppressed contact. Drafting is harmless on its own, but a
    // draft sitting in the pane next to a "Do Not Contact" badge is an
    // invitation to paste it into a mail client.
    if (selected.doNotContact || selected.stage === "Do Not Contact") {
      setDraft("");
      setSaveNote("This contact is suppressed. No outreach may be drafted or sent.");
      return;
    }
    setDraft(outreachFor(selected));
    if (selected.stage === "Qualified" || selected.stage === "New") await updateStage("Outreach Ready");
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <div className="brand">BUILD<span>PIPELINE</span></div>
          <p className="muted">Automated SDR Operating System</p>
        </div>
        <nav>
          {["Pipeline","Prospects","Campaigns","Outreach","Analytics"].map(item => (
            <button
              key={item}
              className={`nav ${view === item ? "active" : ""}`}
              onClick={() => setView(item)}
            >
              {item}
            </button>
          ))}
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

        {view === "Prospects" && (
          <section className="card">
            <div className="cardHead"><div><h2>Prospects</h2><p>Every prospect in this workspace, newest scoring first.</p></div></div>
            <div className="tableWrap">
              <table>
                <thead><tr><th>Company</th><th>Contact</th><th>Email</th><th>Phone</th><th>Location</th><th>Score</th><th>Stage</th><th>Source</th></tr></thead>
                <tbody>
                  {leads.map(lead => (
                    <tr key={lead.id} onClick={() => setSelected(lead)} className={selected?.id === lead.id ? "selected" : ""}>
                      <td><strong>{lead.company}</strong><span>{lead.services}</span></td>
                      <td>{lead.contact || "\u2014"}</td>
                      <td>{lead.email || "\u2014"}</td>
                      <td>{lead.phone || "\u2014"}</td>
                      <td>{[lead.city, lead.state].filter(Boolean).join(", ") || "\u2014"}</td>
                      <td><span className={`score ${lead.score >= 85 ? "hot" : lead.score >= 60 ? "warm" : ""}`}>{lead.score}</span></td>
                      <td>{lead.stage}</td>
                      <td>{lead.source}</td>
                    </tr>
                  ))}
                  {!leads.length && <tr><td colSpan={8} className="muted">No prospects yet. {connection.detail}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === "Campaigns" && (
          <section className="card">
            <div className="cardHead"><div><h2>Campaigns</h2><p>ICP criteria are data. Change the threshold and re-score — no deploy.</p></div></div>
            {!campaigns.length && <p className="muted">No campaigns. {connection.detail}</p>}
            {campaigns.map(campaign => (
              <div key={campaign.id} className="card" style={{marginTop:14}}>
                <h3>{campaign.name} <span className="muted">({campaign.status})</span></h3>
                <div className="row"><span>Objective</span><strong>{campaign.objective}</strong></div>
                <div className="row">
                  <span>Qualified at</span>
                  <input
                    type="number" min={0} max={100} defaultValue={campaign.icp?.qualified_at ?? 60}
                    onBlur={e => updateThreshold(campaign, e.target.value)}
                    style={{width:72}}
                  />
                </div>
                <div className="row"><span>Cadence (days)</span><strong>{(campaign.sequence_days || []).join(", ") || "\u2014"}</strong></div>
                <div className="row"><span>Target states</span><strong>{(campaign.icp?.target_states || []).join(", ") || "any"}</strong></div>
                <label>Category weights</label>
                <div className="flow">
                  {Object.entries(campaign.icp?.category_weights || {})
                    .sort((a,b) => b[1]-a[1])
                    .map(([name, points]) => <b key={name}>{name} +{points}</b>)}
                </div>
                <label>Never contacted ({(campaign.icp?.exclude_terms || []).length} terms)</label>
                <p className="muted">{(campaign.icp?.exclude_terms || []).join(" \u00b7 ")}</p>
              </div>
            ))}
          </section>
        )}

        {view === "Analytics" && (
          <section className="card">
            <div className="cardHead"><div><h2>Analytics</h2><p>Counts come from the CRM, so they match the system of record.</p></div></div>
            <div className="metrics">
              <Metric label="Prospects" value={metrics.total} />
              <Metric label="Qualified" value={metrics.qualified} />
              <Metric label="Contacted" value={metrics.contacted} />
              <Metric label="Calls Booked" value={metrics.meetings} />
            </div>
            <label>By stage</label>
            <div className="flow">
              {stages.map(stage => {
                const count = leads.filter(l => l.stage === stage).length;
                return count ? <b key={stage}>{stage}: {count}</b> : null;
              })}
            </div>
            {/* Reply rate, booking rate and revenue per meeting are Phase 11 and
                need message and meeting records that do not exist yet. Showing
                a zero for them would read as "none happened" rather than "not
                measured", so they are left out until they are real. */}
            <p className="muted">Reply, booking and revenue metrics arrive with the message and meeting records (Phase 11). Not shown rather than shown as zero.</p>
          </section>
        )}

        {(view === "Pipeline" || view === "Outreach") && (<>
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
                    <tr key={lead.id} onClick={() => {
                      setSelected(lead);
                      // The guard has to be here too: this is what actually put
                      // a drafted email on screen for an opted-out contact.
                      setDraft(lead.doNotContact || lead.stage === "Do Not Contact" ? "" : outreachFor(lead));
                    }} className={selected?.id === lead.id ? "selected" : ""}>
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

                {/* The suppression state, stated before anything that could act
                    on this record. It is one-way in the CRM, so there is no
                    toggle here — a control that appeared to undo it would
                    misrepresent what the record does. */}
                {suppressed && (
                  <p className="muted"><strong>Do not contact.</strong> This contact opted out. No outreach, no sequence, no draft.</p>
                )}

                <button onClick={qualify} disabled={busy}>Re-score Prospect</button>
                <label>Pipeline Stage</label>
                <select value={selected.stage} disabled={busy} onChange={e => updateStage(e.target.value)}>
                  {stages.map(s => <option key={s}>{s}</option>)}
                </select>

                {/* What the last action actually did. Before this, a change the
                    CRM never received looked exactly like one it saved. */}
                {saveNote && <p className="muted">{saveNote}</p>}

                <button className="primary full" onClick={generate} disabled={busy || suppressed}>Generate Personalized Outreach</button>

                {/* Why this prospect fits, from the campaign's own ICP reasons
                    rather than re-derived here, so the prose and the number
                    cannot disagree. */}
                {brief?.qualification?.summary && (
                  <>
                    <label>Qualification</label>
                    <p className="muted">{brief.qualification.summary}</p>
                    {/* The brief re-evaluates against the campaign ICP live, so
                        it can disagree with the number stored on the record —
                        after an ICP edit, or after the prospect gained a phone
                        number. Showing both without saying which is which is
                        how an operator loses confidence in the score. */}
                    {typeof brief.qualification.score === "number"
                      && brief.qualification.score !== selected.score && (
                      <p className="muted">
                        Stored score is {selected.score}; against the current ICP this
                        re-evaluates to {brief.qualification.score}. Re-score to update the record.
                      </p>
                    )}
                  </>
                )}
                {brief && !brief.qualification && (
                  <p className="muted">{brief.qualification_unavailable}</p>
                )}

                {brief?.next_action && (
                  <>
                    <label>Next action</label>
                    <p className="muted">
                      {brief.next_action.action}
                      {brief.next_action.requires_human ? " (needs a person)" : ""}
                    </p>
                  </>
                )}

                {brief?.last_reply && (
                  <>
                    <label>Last reply</label>
                    <p className="muted">
                      Read as <strong>{brief.last_reply.classification?.intent}</strong>
                      {brief.last_reply.classification?.objections?.length
                        ? ` · objections: ${brief.last_reply.classification.objections.join(", ")}`
                        : ""}
                    </p>
                  </>
                )}

                {/* Logging a reply is the one thing that needs no send switch
                    and no credential, so it is the part of the loop that can
                    run today: outreach goes out by hand, the answer comes back
                    in here, and the classification decides whether anything
                    further may be sent. */}
                <label>Log an inbound reply</label>
                <textarea
                  rows={4}
                  value={replyText}
                  placeholder="Paste what they wrote back. An opt-out suppresses the contact."
                  onChange={e => setReplyText(e.target.value)}
                />
                <button onClick={logReply} disabled={busy || !replyText.trim()}>Record Reply</button>
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
            {/* A suppressed contact gets no draft, no copy button and no "mark
                sent". The classifier suppressing them in the database is only
                half the guarantee — a ready-to-paste email sitting under a
                "Do not contact" badge is an invitation to send it, and nothing
                in the backend can stop a human copying text off a screen. */}
            {suppressed ? (
              <p className="muted">
                This contact opted out. No message is drafted for them, and none may be sent.
              </p>
            ) : (
              <>
                <textarea value={draft} onChange={e => setDraft(e.target.value)} />
                <div className="actions">
                  <button onClick={() => navigator.clipboard?.writeText(draft)}>Copy</button>
                  {/* Both of these persist through the CRM — "call booked" is the
                      number this product exists to produce, and it used to live
                      in React state only. */}
                  <button onClick={() => updateStage("Contacted")} disabled={busy}>Mark Sent</button>
                  <button onClick={() => updateStage("Call Booked")} disabled={busy}>Mark Call Booked</button>
                </div>
              </>
            )}
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
        </>)}

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
