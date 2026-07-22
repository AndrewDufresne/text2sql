// Cube runtime config — Phase 5 baseline.
// Schema files live under /cube/conf/schema (mounted from config/cube/schema).
// Phase 6: enable JWT and securityContext-based row-level security
// using the LangGraph-injected {user_id, role, business_unit} claims.
module.exports = {
  schemaPath: 'schema',
};
