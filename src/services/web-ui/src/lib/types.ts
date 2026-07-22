// Mirrors the Pydantic contracts in services/langgraph-app + packages/contracts.
// We keep types narrow — the UI only needs what it renders.

export type UserRole = "RM" | "ANALYST" | "ADMIN" | "AUDITOR";

export interface UserCtx {
  id: string;
  role: UserRole;
  business_unit: string;
}

export interface QueryRequest {
  trace_id: string;
  user: UserCtx;
  session_id?: string | null;
  question: string;
}

export interface QueryResult {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  row_count: number;
  truncated?: boolean;
}

export interface QueryError {
  code: string;
  message: string;
  hints?: string[];
}

export interface QueryResponse {
  trace_id: string;
  status: "ok" | "refused" | "error" | string;
  sql?: string | null;
  result?: QueryResult | null;
  explanation?: string | null;
  metrics_used?: string[];
  tables_used?: string[];
  model?: string | null;
  prompt_version?: string | null;
  cost_usd?: number;
  latency_ms?: number;
  error?: QueryError | null;
  output_mask?: {
    enabled: boolean;
    cells_scanned: number;
    cells_masked: number;
    explanation_masked: boolean;
    entity_counts: Record<string, number>;
  } | null;
  feedback_url?: string;
}

export interface GlossaryItem {
  term: string;
  definition: string;
  source: string;
}

export interface ExampleItem {
  category: string;
  question: string;
}

export interface Capabilities {
  version: string;
  product: string;
  data_domain: string;
  can: string[];
  cannot: string[];
  limits: Record<string, number>;
  allowlisted_tables: string[];
  redacted_pii_entities: string[];
}

export interface ChatThread {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  thread_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  query_id: string | null;
  payload: QueryResponse | null;
  created_at: string;
}
