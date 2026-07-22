"""Schema catalog — Phase 2.

Hand-curated table cards drive both:
  1. RAG schema-linking (embed `description + columns` → top-K retrieval)
  2. Fallback prompt (when retrieval is empty / disabled)

Phase 3 will replace these constants with a Cube `/meta` lookup. Until then
this is the *single source of truth* for what the LLM is told about the schema.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableCard:
    name: str
    description: str
    columns: tuple[str, ...]

    @property
    def card_text(self) -> str:
        cols = ", ".join(self.columns)
        return f"Table {self.name}: {self.description}\nColumns: {cols}"


CLIENT_CARD = TableCard(
    name="client",
    description=(
        "CIB customer master. One row per legal entity / customer. Joins to "
        "account and exposure on cif_id. Holds AUM, country, industry, risk "
        "rating, onboarding date and active flag."
    ),
    columns=(
        "cif_id (varchar, PK)",
        "legal_name (varchar)",
        "country_iso (char(2))",
        "industry (varchar)",
        "rm_owner (varchar, RM email)",
        "aum_usd (numeric)",
        "risk_rating (varchar AAA..CCC)",
        "onboarded_at (date)",
        "is_active (boolean)",
    ),
)

ACCOUNT_CARD = TableCard(
    name="account",
    description=(
        "Banking accounts held by clients. One client may have many accounts. "
        "Tracks LOAN / DEPOSIT / FX / DERIV products, currency, balance and "
        "open/closed state. Join to client on cif_id."
    ),
    columns=(
        "account_id (varchar, PK)",
        "cif_id (varchar, FK->client.cif_id)",
        "account_type (varchar LOAN|DEPOSIT|FX|DERIV)",
        "currency (char(3))",
        "balance_usd (numeric)",
        "opened_at (date)",
        "is_closed (boolean)",
    ),
)

EXPOSURE_CARD = TableCard(
    name="exposure",
    description=(
        "Credit exposure facilities booked against clients: term loans, "
        "revolving credit (RCF), trade finance and interest-rate swaps. "
        "Notional, drawn amount, probability of default in basis points, "
        "booked and maturity dates. Join to client on cif_id. "
        "IMPORTANT exact column names: notional_usd (NOT committed_amount_usd), "
        "drawn_usd (NOT drawn_amount_usd), pd_bps (NOT probability_of_default)."
    ),
    columns=(
        "exposure_id (varchar, PK)",
        "cif_id (varchar, FK->client.cif_id)",
        "product (varchar TERM_LOAN|RCF|TRADE_FIN|IRS)",
        "notional_usd (numeric)",
        "drawn_usd (numeric)",
        "pd_bps (integer, basis points)",
        "booked_at (date)",
        "matures_at (date)",
    ),
)

# ---- Phase 5 — extended CIB domain (reference + facts + history) ----

COUNTRY_REF_CARD = TableCard(
    name="country_ref",
    description=(
        "Country reference. ISO-2 code -> name, region (APAC/EMEA/NAM/LATAM), "
        "AML risk_tier (LOW/MED/HIGH/SANCT) and FATF grey-list flag. "
        "Join to client.country_iso for region/risk reporting. "
        "NOTE: risk_tier and is_fatf_grey live HERE on country_ref, NOT on client. "
        "Always join client c JOIN country_ref cr ON c.country_iso = cr.country_iso."
    ),
    columns=(
        "country_iso (char(2), PK)",
        "country_name (varchar)",
        "region (varchar APAC|EMEA|NAM|LATAM)",
        "risk_tier (varchar LOW|MED|HIGH|SANCT)",
        "is_fatf_grey (boolean)",
    ),
)

INDUSTRY_REF_CARD = TableCard(
    name="industry_ref",
    description=(
        "Industry reference. Maps industry name to broad sector "
        "(Cyclical/Defensive/Tech/Financial), NAICS top code and ESG focus flag. "
        "Join to client.industry."
    ),
    columns=(
        "industry (varchar, PK)",
        "sector (varchar Cyclical|Defensive|Tech|Financial)",
        "naics_top (varchar)",
        "is_esg_focus (boolean)",
    ),
)

FX_RATE_CARD = TableCard(
    name="fx_rate",
    description=(
        "Daily FX spot rates expressed as USD per 1 unit of currency. "
        "Use for currency conversion of native amounts in account, daily_balance "
        "and transaction tables. PK is (rate_date, currency)."
    ),
    columns=(
        "rate_date (date)",
        "currency (char(3))",
        "usd_per_unit (numeric, 1 unit ccy = X USD)",
    ),
)

TRANSACTION_CARD = TableCard(
    name="transaction",
    description=(
        "Account-level transaction fact table: payments, drawdowns, repayments, "
        "fee and interest events. Native-currency amount + date. Join account_id "
        "-> account, then account.cif_id -> client. Convert via fx_rate."
    ),
    columns=(
        "txn_id (bigserial, PK)",
        "account_id (varchar, FK->account.account_id)",
        "txn_type (varchar PAYMENT|DRAWDOWN|REPAYMENT|FEE|INTEREST)",
        "amount_native (numeric)",
        "currency (char(3))",
        "txn_date (date)",
        "description (varchar)",
        "counterparty (varchar)",
    ),
)

DAILY_BALANCE_CARD = TableCard(
    name="daily_balance",
    description=(
        "End-of-day balance snapshot per account. Both native amount and "
        "USD-converted amount (already FX-converted using daily fx_rate). "
        "Use this for time-series / trend / period-over-period analytics. "
        "PK is (balance_date, account_id)."
    ),
    columns=(
        "balance_date (date)",
        "account_id (varchar, FK->account.account_id)",
        "balance_native (numeric)",
        "balance_usd (numeric, already FX-converted)",
    ),
)

COVENANT_CARD = TableCard(
    name="covenant",
    description=(
        "Financial covenants attached to credit exposures (DSCR, leverage, "
        "min-EBITDA, NWC). Tracks threshold, test frequency and last test "
        "status (PASS/WAIVED/BREACH). Join exposure_id -> exposure. "
        "NOTE: covenant has NO cif_id column. To get the client, go through "
        "exposure: covenant cov JOIN exposure e ON cov.exposure_id = e.exposure_id "
        "JOIN client c ON e.cif_id = c.cif_id."
    ),
    columns=(
        "covenant_id (serial, PK)",
        "exposure_id (varchar, FK->exposure.exposure_id)",
        "covenant_type (varchar DSCR|LEVERAGE|MIN_EBITDA|NWC)",
        "threshold (numeric)",
        "test_freq (varchar QUARTERLY|SEMIANNUAL|ANNUAL)",
        "last_tested (date)",
        "last_status (varchar PASS|WAIVED|BREACH)",
    ),
)

COLLATERAL_CARD = TableCard(
    name="collateral",
    description=(
        "Collateral pledged against exposures: cash, equity, property, "
        "receivables or guarantees. Tracks market value, regulatory haircut "
        "and last valuation date. Effective collateral = market_value * (1 - haircut/100)."
    ),
    columns=(
        "collateral_id (serial, PK)",
        "exposure_id (varchar, FK->exposure.exposure_id)",
        "collateral_type (varchar CASH|EQUITY|PROPERTY|RECEIVABLES|GUARANTEE)",
        "market_value_usd (numeric)",
        "haircut_pct (numeric, percent)",
        "valuation_date (date)",
    ),
)

RATING_HISTORY_CARD = TableCard(
    name="rating_history",
    description=(
        "Client risk rating SCD2 history. Each row is an effective period "
        "(effective_from..effective_to, NULL=current) with the rating in "
        "effect and the change_reason (INITIAL/ANNUAL_REVIEW/UPGRADE/DOWNGRADE/WATCHLIST)."
    ),
    columns=(
        "history_id (serial, PK)",
        "cif_id (varchar, FK->client.cif_id)",
        "rating (varchar AAA..CCC)",
        "effective_from (date)",
        "effective_to (date, NULL=current)",
        "change_reason (varchar)",
    ),
)


ALL_CARDS: tuple[TableCard, ...] = (
    CLIENT_CARD, ACCOUNT_CARD, EXPOSURE_CARD,
    COUNTRY_REF_CARD, INDUSTRY_REF_CARD,
    FX_RATE_CARD, TRANSACTION_CARD, DAILY_BALANCE_CARD,
    COVENANT_CARD, COLLATERAL_CARD, RATING_HISTORY_CARD,
)

# Hard allowlist for sql_validate (table-name level).
ALLOWED_TABLES: frozenset[str] = frozenset(c.name for c in ALL_CARDS)


def card_by_name(name: str) -> TableCard | None:
    for c in ALL_CARDS:
        if c.name == name:
            return c
    return None


def render_prompt_schema(cards: list[TableCard] | None = None) -> str:
    """Render a schema description block for the system prompt.

    If `cards` is None or empty, dump the full catalog (fallback). Otherwise
    dump only the supplied cards (RAG output).
    """
    use = list(cards) if cards else list(ALL_CARDS)
    body = "\n\n".join(c.card_text for c in use)
    return (
        "Database: Trino over PostgreSQL\n"
        "Catalog.Schema: cib.public\n"
        "Allowed tables (the ONLY tables you may reference):\n\n"
        f"{body}"
    )


# Back-compat: kept so any Phase-1 import path still resolves.
CLIENT_SCHEMA_PROMPT = render_prompt_schema([CLIENT_CARD])
