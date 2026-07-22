"""Self-describing capability surface.

Three read-only endpoints feed the UI capability panel:

  GET /api/v1/glossary       — business terms the assistant understands
  GET /api/v1/capabilities   — what the system can / cannot do, with limits
  GET /api/v1/examples       — curated questions for the empty state

Glossary is a hand-curated list keyed off the schema cards in
`app/schema_catalog.py` plus a few cross-table concepts (active client, AUM,
exposure utilisation, KYC overdue, …). DataHub stays the source of truth in
production; this module is the cached fallback that always renders, even if
DataHub is down or being re-ingested.
"""

from __future__ import annotations

from typing import Any

# Each row: {term, definition, source} where source is human-readable.
GLOSSARY: list[dict[str, str]] = [
    # ---- entities ----
    {"term": "client",
     "definition": "A CIB customer / legal entity. One row per CIF in the `client` table.",
     "source": "client"},
    {"term": "active client",
     "definition": "A client with `is_active = TRUE` in the `client` table.",
     "source": "client.is_active"},
    {"term": "RM",
     "definition": "Relationship Manager. Owner email lives in `client.rm_owner`.",
     "source": "client.rm_owner"},
    {"term": "BU",
     "definition": "Business Unit. Pilot scopes the user to e.g. CIB-APAC.",
     "source": "user.business_unit"},
    # ---- money ----
    {"term": "AUM",
     "definition": "Assets Under Management, in USD. Column `client.aum_usd`.",
     "source": "client.aum_usd"},
    {"term": "balance",
     "definition": "Account-level money. `account.balance_usd` is the spot snapshot; "
                   "`daily_balance.balance_usd` is FX-converted end-of-day series.",
     "source": "account, daily_balance"},
    {"term": "exposure",
     "definition": "Credit facility booked against a client (TERM_LOAN, RCF, TRADE_FIN, IRS). "
                   "Notional and drawn amounts in USD.",
     "source": "exposure"},
    {"term": "utilisation",
     "definition": "exposure.drawn_usd / exposure.notional_usd, as a fraction 0..1.",
     "source": "exposure (derived)"},
    {"term": "PD",
     "definition": "Probability of default, basis points. `exposure.pd_bps` (1bp = 0.01%).",
     "source": "exposure.pd_bps"},
    # ---- risk / regulatory ----
    {"term": "risk rating",
     "definition": "Internal credit rating (AAA, AA, A, BBB, BB, B, CCC). "
                   "`client.risk_rating` is current; history in `risk_rating_history`.",
     "source": "client.risk_rating, risk_rating_history"},
    {"term": "investment grade",
     "definition": "risk_rating IN ('AAA','AA','A','BBB').",
     "source": "client.risk_rating"},
    {"term": "high yield",
     "definition": "risk_rating IN ('BB','B','CCC').",
     "source": "client.risk_rating"},
    {"term": "KYC overdue",
     "definition": "Latest `kyc_event` review for the client is older than 365 days.",
     "source": "kyc_event"},
    {"term": "FATF grey",
     "definition": "Country flagged on the FATF grey list. `country_ref.is_fatf_grey = TRUE`.",
     "source": "country_ref.is_fatf_grey"},
    {"term": "sanctioned country",
     "definition": "country_ref.risk_tier = 'SANCT'. Cross-BU access requires elevated role.",
     "source": "country_ref.risk_tier"},
    # ---- regions ----
    {"term": "APAC",
     "definition": "country_ref.region = 'APAC'.",
     "source": "country_ref.region"},
    {"term": "EMEA",
     "definition": "country_ref.region = 'EMEA'.",
     "source": "country_ref.region"},
    {"term": "NAM",
     "definition": "country_ref.region = 'NAM' (North America).",
     "source": "country_ref.region"},
    {"term": "LATAM",
     "definition": "country_ref.region = 'LATAM'.",
     "source": "country_ref.region"},
    # ---- time ----
    {"term": "Q1 / Q2 / Q3 / Q4",
     "definition": "Calendar quarters. Q3 = Jul-Sep of the most recent year in the data.",
     "source": "date arithmetic"},
    {"term": "YTD",
     "definition": "Year-to-date. From Jan 1 of the current year up to today.",
     "source": "date arithmetic"},
    {"term": "MTD",
     "definition": "Month-to-date.",
     "source": "date arithmetic"},
    # ---- transactions ----
    {"term": "drawdown",
     "definition": "transaction with `txn_type = 'DRAWDOWN'` against a loan account.",
     "source": "transaction.txn_type"},
    {"term": "repayment",
     "definition": "transaction with `txn_type = 'REPAYMENT'`.",
     "source": "transaction.txn_type"},
    # ---- governance ----
    {"term": "covenant breach",
     "definition": "covenant.last_status = 'BREACH' on an active exposure.",
     "source": "covenant.last_status"},
    {"term": "collateral haircut",
     "definition": "Regulatory discount applied to collateral market value. "
                   "Effective value = market_value * (1 - haircut/100).",
     "source": "collateral.haircut"},
    {"term": "FX",
     "definition": "Daily spot rate. `fx_rate.usd_per_unit` converts native amount to USD.",
     "source": "fx_rate"},
]


# Allow-listed tables — kept in sync with OPA Rego policy + schema_catalog.
ALLOWED_TABLES: tuple[str, ...] = (
    "client",
    "account",
    "exposure",
    "transaction",
    "daily_balance",
    "covenant",
    "collateral",
    "kyc_event",
    "trade_event",
    "country_ref",
    "industry_ref",
    "fx_rate",
    "risk_rating_history",
)


CAPABILITIES: dict[str, Any] = {
    "version": "1.0.0-rc1",
    "product": "CIB Text-to-SQL Assistant",
    "data_domain": "CIB pilot warehouse (Trino catalog `cib.public`)",
    "can": [
        "Answer ad-hoc analytical questions over the allow-listed tables.",
        "Auto-redact PII (names, IBANs, phone numbers) before sending your "
        "question to the LLM and after executing SQL.",
        "Explain the answer in plain English with the SQL it ran.",
        "Self-repair one-shot when the first SQL draft fails validation.",
        "Trace every step in Langfuse with PII-safe spans.",
    ],
    "cannot": [
        "Modify data — INSERT / UPDATE / DELETE / DDL are blocked at the SQL-guard.",
        "Cross your business unit without an elevated role (enforced by OPA).",
        "Return more than 10,000 rows in a single query.",
        "Access tables outside the allow list below.",
    ],
    "limits": {
        "row_limit_default": 1000,
        "row_limit_hard_max": 10_000,
        "self_repair_max": 1,
        "llm_timeout_s": 120,
    },
    "allowlisted_tables": list(ALLOWED_TABLES),
    "redacted_pii_entities": [
        "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "IBAN_CODE",
        "CREDIT_CARD", "IP_ADDRESS",
    ],
}


# Curated examples for the empty state. Mirrors the highest-value cases in
# tests/eval/golden_set.yaml so passing eval == real users see the same
# happy paths.
EXAMPLES: list[dict[str, str]] = [
    {"category": "Counts",
     "question": "How many active clients are there in APAC?"},
    {"category": "Counts",
     "question": "Count exposures by product type for investment-grade clients."},
    {"category": "Rankings",
     "question": "Top 10 clients by AUM in the Energy industry."},
    {"category": "Rankings",
     "question": "Top 5 RMs by total drawn exposure last quarter."},
    {"category": "Risk",
     "question": "Which clients have a covenant breach on an active exposure?"},
    {"category": "Risk",
     "question": "List clients with KYC review overdue more than 365 days."},
    {"category": "Trend",
     "question": "Daily total balance USD for the last 30 days."},
    {"category": "Cross-table",
     "question": "Compare total exposure between APAC and EMEA, by product.",
    },
]
