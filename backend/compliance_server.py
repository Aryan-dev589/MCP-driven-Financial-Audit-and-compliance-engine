"""
compliance_server.py
---------------------------------------------------------------------------
Standalone FastMCP server for the Financial Audit & Compliance Engine.

Exposes:
  RESOURCE  policy://expense_rules   -> full Markdown text of the HR Expense Policy
  TOOL      audit_transaction(vendor, amount) -> structured compliance verdict

Run standalone for debugging:
    python compliance_server.py

The FastAPI backend (main.py) launches this as a subprocess over stdio and
talks to it via the official MCP ClientSession — this file never imports
FastAPI or Gemini, keeping the compliance logic fully decoupled.
---------------------------------------------------------------------------
"""

from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ComplianceServer")

POLICY_PATH = Path(__file__).parent / "mock_data" / "expense_policy.md"


# ---------------------------------------------------------------------------
# RESOURCE
# ---------------------------------------------------------------------------
@mcp.resource("policy://expense_rules")
def get_expense_policy() -> str:
    """Returns the full text of the company's HR Expense Policy (Markdown)."""
    return POLICY_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# RULE ENGINE — the business logic backing the audit tool.
# In production this table could itself be loaded/derived from the policy
# document via an LLM extraction pass; it's kept explicit here so the audit
# outcomes are deterministic and easy to demo.
# ---------------------------------------------------------------------------
RULES = [
    {
        "id": "EXP-04.2",
        "category": "meals",
        "vendor_keywords": ["restaurant", "cafe", "steakhouse", "grille", "grill", "bistro", "diner"],
        "max_amount": 150.00,
        "clause": "Section 4.2 — Client & Team Meals",
        "text": "Meals with clients or team capped at $150/person without VP pre-approval.",
    },
    {
        "id": "EXP-06.1",
        "category": "travel_lodging",
        "vendor_keywords": ["hotel", "marriott", "hilton", "hyatt", "inn", "resort"],
        "max_amount": 400.00,
        "clause": "Section 6.1 — Lodging",
        "text": "Lodging capped at $400/night in Tier-1 cities.",
    },
    {
        "id": "EXP-08.3",
        "category": "software",
        "vendor_keywords": ["saas", "software", "subscription", "adobe", "microsoft", "figma", "slack", "creative cloud"],
        "max_amount": 5000.00,
        "clause": "Section 8.3 — Software & SaaS",
        "text": "Software purchases over $5,000 require CTO office sign-off.",
    },
    {
        "id": "EXP-09.5",
        "category": "entertainment",
        "vendor_keywords": ["bar", "lounge", "club", "casino", "spa"],
        "max_amount": 0.00,
        "clause": "Section 9.5 — Prohibited Categories",
        "text": "Entertainment, alcohol-only venues, and spa expenses are non-reimbursable.",
    },
]

DEFAULT_RULE = {
    "id": "EXP-12.0",
    "category": "general",
    "clause": "Section 12.0 — General Business Expense",
    "text": "General business expenses capped at $1,000 without manager approval.",
    "max_amount": 1000.00,
}


def _match_rule(vendor: str) -> dict:
    vendor_lower = vendor.lower()
    for rule in RULES:
        if any(kw in vendor_lower for kw in rule["vendor_keywords"]):
            return rule
    return DEFAULT_RULE


# ---------------------------------------------------------------------------
# TOOL
# ---------------------------------------------------------------------------
@mcp.tool()
def audit_transaction(vendor: str, amount: float) -> dict:
    """
    Audits a single financial transaction against the corporate HR Expense Policy.

    Args:
        vendor: Vendor / merchant name as extracted from the invoice.
        amount: Transaction amount in USD.

    Returns:
        A dict describing the compliance verdict, matched rule, plain-English
        reason, and a precise citation into the policy document.
    """
    rule = _match_rule(vendor)
    cap = rule["max_amount"]

    if cap == 0.00:
        status = "REJECTED"
        reason = f"'{vendor}' falls under a prohibited category and is non-reimbursable regardless of amount."
    elif amount > cap:
        status = "REJECTED"
        reason = f"Amount ${amount:,.2f} exceeds the policy cap of ${cap:,.2f} for this category."
    elif amount > cap * 0.85:
        status = "FLAGGED"
        reason = (
            f"Amount ${amount:,.2f} is within policy (cap ${cap:,.2f}) but close enough to the "
            f"limit to warrant manager review."
        )
    else:
        status = "APPROVED"
        reason = f"Amount ${amount:,.2f} is within the ${cap:,.2f} cap for this category."

    return {
        "vendor": vendor,
        "amount": amount,
        "status": status,
        "rule_id": rule["id"],
        "clause": rule["clause"],
        "policy_text": rule["text"],
        "reason": reason,
        "citation": f"expense_policy.md § {rule['clause']}",
    }


if __name__ == "__main__":
    # stdio transport — this is what main.py's stdio_client subprocess launches
    mcp.run(transport="stdio")
