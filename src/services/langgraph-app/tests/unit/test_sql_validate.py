"""Unit tests for the sql_validate node — the security floor of Phase 1.

50+ cases covering: legal queries, DDL/DML, multi-statement, table allowlist,
LIMIT injection, edge whitespace.
"""

from __future__ import annotations

import pytest

from app.nodes.sql_validate import validate


# --- Helpers ---------------------------------------------------------------


def _ok(sql: str):
    r = validate(sql)
    assert r.safe, f"expected safe but got violations={r.violations}"
    return r


def _bad(sql: str, *, contains: str | None = None):
    r = validate(sql)
    assert not r.safe, f"expected unsafe but got safe; sql={sql}"
    if contains:
        joined = " | ".join(r.violations)
        assert contains in joined, f"violation '{contains}' not in {joined}"
    return r


# --- Legal SELECTs ---------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM client LIMIT 10",
        "SELECT cif_id, legal_name FROM client WHERE country_iso = 'US' LIMIT 5",
        "SELECT count(*) FROM client",
        "SELECT industry, sum(aum_usd) FROM client GROUP BY industry LIMIT 100",
        "WITH active AS (SELECT * FROM client WHERE is_active) SELECT count(*) FROM active",
        "SELECT * FROM client ORDER BY aum_usd DESC LIMIT 5",
        "  select cif_id from client limit 1  ",
        "SELECT cif_id FROM client WHERE rm_owner = 'alice@bank' LIMIT 50",
        # Phase 2: account + exposure are now in the allowlist
        "SELECT * FROM account LIMIT 1",
        "SELECT sum(drawn_usd) FROM exposure LIMIT 1",
        "SELECT c.cif_id FROM client c JOIN account a ON c.cif_id = a.cif_id LIMIT 1",
    ],
)
def test_legal_selects(sql: str) -> None:
    r = _ok(sql)
    # at least one allowed table must be present
    assert {"client", "account", "exposure"} & set(r.tables_used)


def test_missing_limit_is_wrapped_not_rejected() -> None:
    r = _ok("SELECT * FROM client")
    assert "LIMIT 1000" in r.sql.upper()


def test_trailing_semicolon_tolerated() -> None:
    _ok("SELECT 1 FROM client LIMIT 1;")


# --- DDL / DML / dangerous ops --------------------------------------------


@pytest.mark.parametrize(
    "sql,kind",
    [
        ("INSERT INTO client (cif_id) VALUES ('X')", "Insert"),
        ("UPDATE client SET aum_usd = 0", "Update"),
        ("DELETE FROM client WHERE 1=1", "Delete"),
        ("DROP TABLE client", "Drop"),
        ("CREATE TABLE foo (x int)", "Create"),
        ("ALTER TABLE client ADD COLUMN x int", "AlterTable"),
        ("TRUNCATE TABLE client", "Truncate"),
        ("MERGE INTO client USING t ON 1=1 WHEN MATCHED THEN DELETE", "Merge"),
    ],
)
def test_forbidden_statements(sql: str, kind: str) -> None:
    _bad(sql, contains="forbidden_statement")


@pytest.mark.parametrize(
    "sql",
    [
        "CALL system.runtime.kill_query('x')",
        "USE cib.public",
        "SET SESSION query_max_run_time = '1h'",
    ],
)
def test_command_statements(sql: str) -> None:
    _bad(sql)


# --- Table allowlist -------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM users LIMIT 1",
        "SELECT * FROM secret_table LIMIT 1",
        "SELECT * FROM client JOIN users ON 1=1 LIMIT 1",
        "SELECT * FROM information_schema.tables LIMIT 1",
        "SELECT * FROM system.runtime.queries LIMIT 1",
    ],
)
def test_table_not_allowed(sql: str) -> None:
    _bad(sql, contains="table_not_allowed")


# --- Multi-statement -------------------------------------------------------


def test_multiple_statements_rejected() -> None:
    _bad("SELECT * FROM client LIMIT 1; SELECT * FROM client LIMIT 1")


# --- Garbage / empty -------------------------------------------------------


@pytest.mark.parametrize("sql", ["", "   ", None])
def test_empty(sql: str | None) -> None:
    r = validate(sql or "")
    assert not r.safe
    assert "empty_sql" in r.violations


def test_unparseable() -> None:
    r = validate("SELEKT *** FROMM (((")
    assert not r.safe
    # sqlglot may emit either a parse_error or a non_select_root depending on version
    joined = " | ".join(r.violations)
    assert ("parse_error" in joined) or ("non_select_root" in joined) or ("forbidden_statement" in joined)


# --- Injection-flavored ----------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM client WHERE 1=1; DROP TABLE client",          # multi-stmt
        "SELECT * FROM client UNION ALL SELECT * FROM password_vault LIMIT 1",  # disallowed table
    ],
)
def test_injection_flavored(sql: str) -> None:
    _bad(sql)
