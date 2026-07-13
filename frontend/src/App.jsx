import React, { useState } from "react";

const API_BASE = "http://localhost:8000";

const SUGGESTED_QUESTIONS = [
  "Can I expense a $600 hotel room?",
  "What's the limit for client dinners?",
  "Can I expense drinks at a bar with a client?",
  "Do I need approval for a $6,000 software purchase?",
];

export default function App() {
  const [mode, setMode] = useState("auditor");

  return (
    <div className="app-shell">
      <header className="masthead">
        <div>
          <h1 className="masthead-title">
            Ledger<span className="accent"> // </span>Audit &amp; Compliance Engine
          </h1>
          <div className="masthead-sub">MCP-driven policy enforcement · demo build</div>
        </div>
        <nav className="mode-toggle">
          <button
            className={mode === "auditor" ? "active" : ""}
            onClick={() => setMode("auditor")}
          >
            Auditor Mode
          </button>
          <button
            className={mode === "copilot" ? "active" : ""}
            onClick={() => setMode("copilot")}
          >
            Copilot Mode
          </button>
        </nav>
      </header>

      <main className="main-area">
        {mode === "auditor" ? <AuditorMode /> : <CopilotMode />}
      </main>
    </div>
  );
}

/* --------------------------------------------------------------------- */
/* AUDITOR MODE                                                          */
/* --------------------------------------------------------------------- */
function AuditorMode() {
  const [fileName, setFileName] = useState("");
  const [extracted, setExtracted] = useState(null);
  const [auditResults, setAuditResults] = useState(null);
  const [loadingStep, setLoadingStep] = useState(null); // 'extract' | 'audit' | null
  const [error, setError] = useState(null);

  async function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    setFileName(file.name);
    setExtracted(null);
    setAuditResults(null);
    setError(null);
    setLoadingStep("extract");

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/upload-invoice`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error("Extraction failed");
      const data = await res.json();
      setExtracted(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingStep(null);
    }
  }

  async function runAudit() {
    if (!extracted) return;
    setLoadingStep("audit");
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/audit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(extracted.line_items),
      });
      if (!res.ok) throw new Error("Audit failed");
      const data = await res.json();
      setAuditResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingStep(null);
    }
  }

  return (
    <>
      <section className="panel">
        <h2>1 · Upload invoice</h2>
        <p className="panel-hint">
          Parsed via LlamaParse + Gemini extraction (mocked locally for this demo — swap in
          live API keys in <code>main.py</code> without touching this UI).
        </p>
        <div className="dropzone">
          <span className="file-label">
            {fileName || "No file selected — any .pdf or .txt works, contents are mocked"}
          </span>
          <label className="btn" style={{ cursor: "pointer" }}>
            Choose invoice
            <input
              type="file"
              onChange={handleFileChange}
              style={{ display: "none" }}
              accept=".pdf,.txt,.png,.jpg"
            />
          </label>
        </div>
        {loadingStep === "extract" && (
          <p className="loading-line" style={{ marginTop: 14 }}>
            ▸ Parsing tables and extracting line items…
          </p>
        )}
      </section>

      {extracted && (
        <section className="panel">
          <h2>2 · Extracted line items</h2>
          <p className="panel-hint">
            Structured output from <code>{extracted.extraction_engine}</code>
          </p>
          <div className="doc-name">Document: {extracted.document_name}</div>
          <table className="ledger-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Description</th>
                <th className="amount-cell">Amount</th>
              </tr>
            </thead>
            <tbody>
              {extracted.line_items.map((item, i) => (
                <tr key={i}>
                  <td>{item.vendor}</td>
                  <td>{item.line_item}</td>
                  <td className="amount-cell">${item.amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 18 }}>
            <button className="btn" onClick={runAudit} disabled={loadingStep === "audit"}>
              {loadingStep === "audit" ? "Auditing…" : "Run compliance audit →"}
            </button>
          </div>
        </section>
      )}

      {auditResults && (
        <section className="panel">
          <h2>3 · Compliance verdicts</h2>
          <p className="panel-hint">
            Each row was routed through the MCP <code>audit_transaction</code> tool against{" "}
            <code>policy://expense_rules</code>.
          </p>
          <table className="ledger-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th className="amount-cell">Amount</th>
                <th>Status</th>
                <th>Rule</th>
              </tr>
            </thead>
            <tbody>
              {auditResults.map((r, i) => (
                <React.Fragment key={i}>
                  <tr>
                    <td>{r.vendor}</td>
                    <td className="amount-cell">${r.amount.toFixed(2)}</td>
                    <td>
                      <span className={`stamp ${r.status}`}>{r.status}</span>
                    </td>
                    <td>{r.rule_id}</td>
                  </tr>
                  <tr>
                    <td colSpan={4} className="reason-row">
                      {r.reason}
                      <br />
                      <span className="citation-tag">↳ {r.citation}</span>
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {error && <p style={{ color: "var(--stamp-red)" }}>{error}</p>}
    </>
  );
}

/* --------------------------------------------------------------------- */
/* COPILOT MODE                                                           */
/* --------------------------------------------------------------------- */
function CopilotMode() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function ask(q) {
    const query = q ?? question;
    if (!query.trim()) return;
    setQuestion(query);
    setLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await fetch(`${API_BASE}/copilot/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: query }),
      });
      if (!res.ok) throw new Error("Copilot request failed");
      const data = await res.json();
      setAnswer(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>Ask about policy</h2>
      <p className="panel-hint">
        Reads <code>policy://expense_rules</code> from the MCP server, then (mocked) Gemini
        rewrites the relevant clause in plain English with an exact citation.
      </p>

      <div className="copilot-input-row">
        <input
          type="text"
          placeholder="e.g. Can I expense a $600 hotel room?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
        />
        <button className="btn" onClick={() => ask()} disabled={loading}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </div>

      <div className="suggested-qs">
        {SUGGESTED_QUESTIONS.map((q) => (
          <button key={q} onClick={() => ask(q)}>
            {q}
          </button>
        ))}
      </div>

      {loading && <p className="loading-line" style={{ marginTop: 16 }}>▸ Retrieving clause and demystifying…</p>}
      {error && <p style={{ color: "var(--stamp-red)", marginTop: 16 }}>{error}</p>}

      {answer && (
        <div className="copilot-answer">
          <p className="plain-english">{answer.answer}</p>
          <div className="clause-block">{answer.raw_clause_text}</div>
          <span className="citation-tag">↳ {answer.citation}</span>
        </div>
      )}

      {!answer && !loading && !error && (
        <p className="empty-state">Ask a question above, or tap a suggestion.</p>
      )}
    </section>
  );
}
