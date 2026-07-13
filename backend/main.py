"""
main.py
---------------------------------------------------------------------------
FastAPI backend for the Financial Audit & Compliance Engine.

Responsibilities:
  1. Accepts invoice uploads and runs them through a (mocked) LlamaParse +
     Gemini extraction pipeline to produce structured line items.
  2. Acts as an MCP CLIENT: launches compliance_server.py over stdio and
     calls its `audit_transaction` TOOL for every extracted line item.
  3. Reads the `policy://expense_rules` RESOURCE from the MCP server and
     answers plain-English policy questions ("Copilot Mode") with a
     (mocked) Gemini call, always returning a precise citation.

Toggle USE_LIVE_GEMINI / USE_LIVE_LLAMAPARSE env vars once you have real
API keys — the mock functions are written as drop-in replacements so the
surrounding structural logic never changes.
---------------------------------------------------------------------------
"""

import os
import re
import json
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE_DIR = Path(__file__).parent
SERVER_SCRIPT = BASE_DIR / "compliance_server.py"

USE_LIVE_GEMINI = os.getenv("USE_LIVE_GEMINI", "false").lower() == "true"
USE_LIVE_LLAMAPARSE = os.getenv("USE_LIVE_LLAMAPARSE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# MCP CLIENT LIFESPAN
# One persistent stdio session to compliance_server.py, held for the life
# of the FastAPI app instead of re-spawning a subprocess per request.
# ---------------------------------------------------------------------------
mcp_session: Optional[ClientSession] = None
_stdio_ctx = None
_session_ctx = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_session, _stdio_ctx, _session_ctx

    server_params = StdioServerParameters(
        command="python",
        args=[str(SERVER_SCRIPT)],
    )

    _stdio_ctx = stdio_client(server_params)
    read, write = await _stdio_ctx.__aenter__()

    _session_ctx = ClientSession(read, write)
    mcp_session = await _session_ctx.__aenter__()
    await mcp_session.initialize()
    print("[MCP] Connected to compliance_server.py")

    yield

    await _session_ctx.__aexit__(None, None, None)
    await _stdio_ctx.__aexit__(None, None, None)
    print("[MCP] Session closed")


app = FastAPI(title="Financial Audit & Compliance Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# MOCK DOCUMENT PARSING — stands in for LlamaParse + Gemini extraction
# ---------------------------------------------------------------------------
MOCK_INVOICE_BANK = [
    {"vendor": "The Capital Grille Steakhouse", "amount": 212.40, "line_item": "Client dinner - 4 guests"},
    {"vendor": "Marriott Downtown Hotel", "amount": 389.00, "line_item": "1 night lodging"},
    {"vendor": "Adobe Creative Cloud (Enterprise)", "amount": 6400.00, "line_item": "Annual SaaS license - Design team"},
    {"vendor": "Ruby Lounge & Bar", "amount": 145.00, "line_item": "Team happy hour"},
    {"vendor": "Hilton Garden Inn", "amount": 255.00, "line_item": "2 nights lodging - offsite"},
    {"vendor": "Figma Enterprise Subscription", "amount": 3200.00, "line_item": "Annual seats renewal"},
    {"vendor": "Office Bistro Catering", "amount": 168.00, "line_item": "Team lunch meeting"},
    {"vendor": "Staples Office Supplies", "amount": 87.25, "line_item": "Office supplies restock"},
]


def mock_llamaparse_extraction(filename: str) -> Dict[str, Any]:
    """
    MOCK of a LlamaParse document-parsing call.

    In production this would send the uploaded PDF to LlamaParse to OCR and
    reconstruct its tables, then hand the raw cells to Gemini for entity
    extraction into a clean schema. Kept deterministic-ish per filename so
    demos are repeatable. Swap the body for:

        from llama_parse import LlamaParse
        parser = LlamaParse(api_key=os.getenv("LLAMA_CLOUD_API_KEY"), result_type="markdown")
        documents = parser.load_data(file_path)
        # documents[0].text now holds the reconstructed Markdown tables
    """
    random.seed(sum(ord(c) for c in filename) or 1)
    n_items = random.randint(2, 4)
    items = random.sample(MOCK_INVOICE_BANK, n_items)
    return {
        "document_name": filename,
        "extraction_engine": "llamaparse-mock-v1" if not USE_LIVE_LLAMAPARSE else "llamaparse-live",
        "line_items": items,
        "raw_table_preview": [
            {"Vendor": i["vendor"], "Description": i["line_item"], "Amount (USD)": f"${i['amount']:,.2f}"}
            for i in items
        ],
    }


def mock_gemini_structuring(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    MOCK of the Gemini call that normalizes/validates LlamaParse's raw table
    extraction into a clean, typed schema before it's routed to the MCP
    audit tool. Swap for:

        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(structuring_prompt)
    """
    return extracted  # mock: passthrough, already clean in this demo


# ---------------------------------------------------------------------------
# MOCK GEMINI COPILOT — plain-English demystification + citation lookup
# ---------------------------------------------------------------------------
def mock_gemini_copilot_answer(question: str, policy_text: str) -> Dict[str, Any]:
    """
    MOCK of a Gemini call that answers a natural-language policy question,
    rewrites the relevant clause in plain English, and cites the exact
    section. Uses lightweight keyword matching against the policy Markdown
    so the demo works with zero API keys. Swap for:

        model = genai.GenerativeModel("gemini-1.5-pro")
        resp = model.generate_content(
            f"Policy document:\n{policy_text}\n\nEmployee question: {question}\n"
            f"Answer in plain English and cite the exact section."
        )
    """
    q = question.lower()
    sections = re.split(r"(?=^## )", policy_text, flags=re.MULTILINE)
    sections = [s for s in sections if s.strip()]

    best_section, best_score = sections[0], -1
    for section in sections:
        score = sum(1 for word in q.split() if len(word) > 3 and word in section.lower())
        if score > best_score:
            best_score, best_section = score, section

    heading_match = re.match(r"## (.+)", best_section.strip())
    clause_title = heading_match.group(1) if heading_match else "General Policy"
    short_title = clause_title.split("—")[-1].strip() if "—" in clause_title else clause_title

    plain_english = (
        f"Here's the plain-English version: for {short_title.lower()}, the policy sets a clear cap "
        f"and approval path — see the exact clause below for numbers. "
        f"(Mocked demystification; wire in Gemini for production-quality rewrites.)"
    )

    return {
        "answer": plain_english,
        "clause_title": clause_title,
        "raw_clause_text": best_section.strip(),
        "citation": f"expense_policy.md § {clause_title}",
    }


# ---------------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------------
class LineItem(BaseModel):
    vendor: str
    amount: float
    line_item: Optional[str] = None


class AuditResult(BaseModel):
    vendor: str
    amount: float
    status: str
    rule_id: str
    clause: str
    policy_text: str
    reason: str
    citation: str


class CopilotRequest(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok", "mcp_connected": mcp_session is not None}


@app.post("/upload-invoice")
async def upload_invoice(file: UploadFile = File(...)):
    """Auditor Mode step 1: parse invoice -> structured line items (mocked LlamaParse + Gemini)."""
    await file.read()  # consume upload stream (kept to mirror the real I/O path)
    extracted = mock_llamaparse_extraction(file.filename or "uploaded_invoice.pdf")
    structured = mock_gemini_structuring(extracted)
    return structured


@app.post("/audit", response_model=List[AuditResult])
async def audit_line_items(line_items: List[LineItem]):
    """Auditor Mode step 2: run each extracted line item through the MCP `audit_transaction` tool."""
    if mcp_session is None:
        raise HTTPException(status_code=503, detail="MCP session not initialized")

    results = []
    for item in line_items:
        tool_result = await mcp_session.call_tool(
            "audit_transaction",
            arguments={"vendor": item.vendor, "amount": item.amount},
        )
        payload = json.loads(tool_result.content[0].text)
        results.append(payload)
    return results


@app.get("/policy")
async def get_policy():
    """Fetch the raw MCP Resource (the policy document) for display/debug."""
    if mcp_session is None:
        raise HTTPException(status_code=503, detail="MCP session not initialized")
    resource = await mcp_session.read_resource("policy://expense_rules")
    text = resource.contents[0].text
    return {"policy_markdown": text}


@app.post("/copilot/ask")
async def copilot_ask(req: CopilotRequest):
    """Copilot Mode: answer a policy question in plain English with a precise citation."""
    if mcp_session is None:
        raise HTTPException(status_code=503, detail="MCP session not initialized")
    resource = await mcp_session.read_resource("policy://expense_rules")
    policy_text = resource.contents[0].text
    answer = mock_gemini_copilot_answer(req.question, policy_text)
    return answer


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
