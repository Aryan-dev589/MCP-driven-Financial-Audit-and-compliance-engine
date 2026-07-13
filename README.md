# Ledger — Financial Audit & Compliance Engine (Prototype)

Unstructured invoices in → policy-checked, cited, plain-English verdicts out.

## Folder structure

```
financial-audit-engine/
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── compliance_server.py      # FastMCP server — RESOURCE + TOOL
│   ├── main.py                   # FastAPI app — MCP client + mocked LlamaParse/Gemini
│   └── mock_data/
│       └── expense_policy.md     # The "corporate rulebook" served as an MCP Resource
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx                # Auditor Mode + Copilot Mode
        └── App.css
```

## Run it

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python main.py
# -> Uvicorn on http://localhost:8000
# main.py spawns compliance_server.py itself over stdio — you don't run it separately.
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
# -> http://localhost:5173
```

Open the frontend, upload any file in Auditor Mode (contents are mocked, so any .pdf/.txt
works), run the audit, then switch to Copilot Mode and ask a policy question.

## How the pieces fit together

- **`compliance_server.py`** is a standalone FastMCP server. It has no knowledge of FastAPI,
  Gemini, or HTTP — it only knows how to serve the policy document as a `Resource`
  (`policy://expense_rules`) and run `audit_transaction(vendor, amount)` as a `Tool`. Test it
  standalone anytime with `python compliance_server.py`.
- **`main.py`** is the FastAPI app *and* the MCP client. On startup it launches
  `compliance_server.py` as a subprocess and holds one persistent `ClientSession` over stdio
  for the app's lifetime (see the `lifespan` context manager). Every `/audit` call fans out to
  `mcp_session.call_tool(...)`; every `/policy` or `/copilot/ask` call reads the resource via
  `mcp_session.read_resource(...)`.
- **Mocked AI steps**: `mock_llamaparse_extraction()` and `mock_gemini_structuring()` stand in
  for the real document-parsing pipeline; `mock_gemini_copilot_answer()` stands in for the
  plain-English rewrite. Each has the real API call pattern written in its docstring — flip
  `USE_LIVE_LLAMAPARSE` / `USE_LIVE_GEMINI` and swap the function body once you have API keys,
  with zero changes needed to the FastAPI routes, the MCP wiring, or the React UI.

## Going to production

1. Drop in real `LLAMA_CLOUD_API_KEY` and `GOOGLE_API_KEY` env vars, uncomment the
   `llama-parse` / `google-generativeai` lines in `requirements.txt`, and replace the mock
   function bodies (docstrings show the exact call shape).
2. Move `RULES` in `compliance_server.py` into a real datastore or derive it from the policy
   doc via an LLM extraction pass, if the rulebook needs to change without a redeploy.
3. Add auth in front of the FastAPI routes; the MCP layer itself is transport-agnostic and can
   move from stdio to a networked transport (SSE/streamable HTTP) if the compliance server
   needs to run on a separate host.
