# OPA policy — text2sql authz
# Decision is `data.text2sql.decision` returning {allow, reasons, matched_policy}.
# Mounted at /policies in the opa container.

package text2sql

import future.keywords.every
import future.keywords.in
import future.keywords.if
import future.keywords.contains

# ---- Per-role table allowlist (Phase 5 extended domain) ----
# Keep this in sync with `app/schema_catalog.py::ALL_CARDS` and
# `app/clients/opa_client.py::_ROLE_TABLES`. Least-privilege: PII tables only
# for Compliance + Admin; credit-risk metrics blocked for Ops.
role_tables := {
    "RM": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
        "exposure","covenant","collateral","rating_history",
    },
    "Risk": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
        "exposure","covenant","collateral","rating_history",
    },
    "Compliance": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
        "exposure","covenant","collateral","rating_history",
        "client_contact","rm_user",
    },
    "Ops": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
    },
    "Finance": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
        "exposure","covenant","collateral","rating_history",
    },
    "Admin": {
        "client","account","country_ref","industry_ref","fx_rate",
        "transaction","daily_balance",
        "exposure","covenant","collateral","rating_history",
        "client_contact","rm_user",
    },
}

# ---- Operations: SELECT only in Phase 2; SQL_UNSAFE bars the rest already ----
allowed_ops := {"SELECT"}

# ---- Aggregate decision ----
default decision := {
    "allow": false,
    "reasons": ["no_match"],
    "matched_policy": "default_deny",
}

decision := result if {
    role := input.user.role
    role_in_allowlist(role)
    every t in input.tables {
        t in role_tables[role]
    }
    every op in input.ops {
        op in allowed_ops
    }
    obligations := row_filter_obligations(role, input.user.id)
    result := {
        "allow": true,
        "reasons": [],
        "matched_policy": sprintf("role:%s", [role]),
        "obligations": obligations,
    }
}

decision := result if {
    role := input.user.role
    not role_in_allowlist(role)
    result := {
        "allow": false,
        "reasons": [sprintf("unknown_role:%s", [role])],
        "matched_policy": "role_unknown",
    }
}

decision := result if {
    role := input.user.role
    role_in_allowlist(role)
    bad := [t | t := input.tables[_]; not t in role_tables[role]]
    count(bad) > 0
    result := {
        "allow": false,
        "reasons": [sprintf("table_not_allowed_for_role:%s:%v", [role, bad])],
        "matched_policy": sprintf("role:%s", [role]),
    }
}

decision := result if {
    role := input.user.role
    role_in_allowlist(role)
    every t in input.tables {
        t in role_tables[role]
    }
    bad := [op | op := input.ops[_]; not op in allowed_ops]
    count(bad) > 0
    result := {
        "allow": false,
        "reasons": [sprintf("op_not_allowed:%v", [bad])],
        "matched_policy": "ops_allowlist",
    }
}

role_in_allowlist(role) if {
    role_tables[role]
}

# ---- Row-level filter obligations ----
# RM: only see clients they own. The row_filter value is a SQL fragment that
# the Python layer injects into the WHERE clause of the validated SQL.
# We use the full table name (not an alias) so the injection function can
# resolve it via sqlglot AST inspection.
row_filter_obligations(role, user_id) := obligations if {
    role == "RM"
    obligations := {"row_filter": sprintf("client.rm_owner = '%s'", [user_id])}
} else := {} if {
    role != "RM"
}
