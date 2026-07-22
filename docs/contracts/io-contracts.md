# 跨层 I/O 契约总表(Contracts)

> 版本:v0.1
> 原则:契约优先(Contract-first)。所有跨进程边界必须有 **schema + 版本号 + trace_id**。
> 工具:Pydantic v2(Python 内)、JSON Schema(语言无关)、OpenAPI(HTTP)、Pact(消费者驱动契约测试,可选)。

---

## 0. 通用规则

### 0.1 公共 Header(所有 HTTP 调用强制)
| Header | 必填 | 说明 |
|---|---|---|
| `X-Trace-Id` | 是 | UUIDv7,LangGraph 入口生成 |
| `X-User-Id` | 是 | 业务用户(如 `alice@bank`) |
| `X-User-Role` | 是 | `RM` / `Risk` / `Compliance` / `Ops` / ... |
| `X-Request-Id` | 是 | 单次 HTTP 请求 ID(子 span) |
| `X-App-Version` | 是 | 调用方版本(`langgraph-app@v0.3.1`) |

### 0.2 公共错误响应
```json
{
  "error": {
    "code": "VALIDATION_FAILED|UNAUTHORIZED|UPSTREAM_ERROR|TIMEOUT|INTERNAL",
    "message": "human readable",
    "details": { "...": "..." },
    "trace_id": "..."
  }
}
```

### 0.3 版本管理
- 接口变更走 **SemVer**:break change → 新路径(`/v2/...`)。
- LangGraph 内部状态字段变更 → `GraphState.schema_version` 升一位。
- Promptfoo 用例必须锁 `prompt_version` + `model_version`。

---

## C1. Browser ↔ Chainlit

- 协议:HTTPS / WebSocket(Chainlit 默认)
- 鉴权:Cookie session(Phase 1 假账户;Phase 2 SSO/OIDC)
- 输入:用户输入文本、👍/👎、修正 SQL
- 输出:流式回复(token-by-token)+ 最终结构化结果

详见 [L7 子架构](../layers/L7-experience.md)。

---

## C2. Chainlit → LangGraph App

**Endpoint**:`POST http://langgraph-app:8080/api/v1/query`

### 请求 Schema(Pydantic 等价 JSON Schema)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["trace_id", "user", "question"],
  "properties": {
    "trace_id": { "type": "string", "format": "uuid" },
    "user": {
      "type": "object",
      "required": ["id", "role", "business_unit"],
      "properties": {
        "id":            { "type": "string" },
        "role":          { "type": "string", "enum": ["RM","Risk","Compliance","Ops","Finance","Admin"] },
        "business_unit": { "type": "string" }
      }
    },
    "session_id":     { "type": "string" },
    "question":       { "type": "string", "minLength": 1, "maxLength": 2000 },
    "clarifications": { "type": "array", "items": { "type": "object" } },
    "preferences":    {
      "type": "object",
      "properties": {
        "row_limit":      { "type": "integer", "default": 1000 },
        "explain_in":     { "type": "string", "enum": ["en","zh"], "default": "en" }
      }
    }
  }
}
```

### 响应 Schema
```json
{
  "type": "object",
  "required": ["trace_id", "status"],
  "properties": {
    "trace_id":     { "type": "string" },
    "status":       { "type": "string", "enum": ["ok","need_clarify","need_approval","refused","error"] },
    "sql":          { "type": "string" },
    "result": {
      "type": "object",
      "properties": {
        "columns":  { "type": "array", "items": { "type": "string" } },
        "rows":     { "type": "array", "items": { "type": "array" } },
        "row_count":{ "type": "integer" },
        "truncated":{ "type": "boolean" }
      }
    },
    "explanation":   { "type": "string" },
    "metrics_used":  { "type": "array", "items": { "type": "string" } },
    "tables_used":   { "type": "array", "items": { "type": "string" } },
    "model":         { "type": "string" },
    "prompt_version":{ "type": "string" },
    "cost_usd":      { "type": "number" },
    "latency_ms":    { "type": "integer" },
    "error":         { "$ref": "#/$defs/Error" }
  }
}
```

---

## C3. LangGraph 节点间(进程内)

**单一可变状态对象 `GraphState`**(Pydantic v2,`frozen=False`)。

```python
class GraphState(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    trace_id: UUID
    request: QueryRequest                 # 见 C2
    intent: Optional[Intent] = None
    pii_findings: list[PIIFinding] = []
    schema_link: Optional[SchemaLinkResult] = None
    sql_draft: Optional[str] = None
    sql_validated: Optional[SqlValidationResult] = None
    opa_decision: Optional[OpaDecision] = None
    explain_plan: Optional[ExplainResult] = None
    execution: Optional[ExecutionResult] = None
    explanation: Optional[str] = None
    spans: list[Span] = []                # 节点级耗时与状态
    errors: list[NodeError] = []
    final: Optional[QueryResponse] = None # 见 C2
```

每个节点签名:`async def node(state: GraphState) -> GraphState`,对 `state` **只追加,不删改历史**(便于回放)。

详见 [L5 子架构](../layers/L5-orchestration.md)。

---

## C4. LangGraph → LiteLLM

**Endpoint**:`POST http://litellm:4000/v1/chat/completions`(OpenAI 兼容)

关键扩展字段(Body):
```json
{
  "model": "router/sql-gen",
  "messages": [...],
  "metadata": {
    "trace_id": "...",
    "user_id": "alice@bank",
    "session_id": "...",
    "generation_name": "sql_generate",
    "tags": ["text2sql","cib"]
  },
  "temperature": 0.0,
  "response_format": { "type": "json_object" }
}
```

- LiteLLM 配置中开启 **Langfuse Callback**,自动把 generation 写入 Langfuse(无需 LangGraph 双写)。
- 路由策略由 `litellm/config.yaml` 控制(见 L4)。

---

## C5. LangGraph → TEI(Text Embeddings Inference)

| 接口 | 方法/路径 | 输入 | 输出 |
|---|---|---|---|
| 嵌入 | `POST /embed` | `{"inputs":["..."]}` | `{"embeddings":[[...]]}` |
| 重排 | `POST /rerank`(独立实例) | `{"query":"...","texts":["..."]}` | `{"results":[{"index":0,"score":0.93}]}` |

约束:
- 单次 `inputs` 长度 ≤ 32(超出由 LangGraph 切片)
- 模型在 TEI 启动参数固定(`bge-m3` / `bge-reranker-v2-m3`),由 `model_card` 元数据校验

---

## C6. LangGraph → Presidio

| 接口 | 路径 | 输入 | 输出 |
|---|---|---|---|
| 分析 | `POST http://presidio-analyzer:5001/analyze` | `{"text":"...","language":"en","entities":["PERSON","CREDIT_CARD",...]}` | `[{"entity_type","start","end","score"}]` |
| 脱敏 | `POST http://presidio-anonymizer:5002/anonymize` | `{"text":"...","analyzer_results":[...],"anonymizers":{...}}` | `{"text":"<masked>", "items":[...]}` |

调用点:
- **入口**:对 `request.question` 调 `analyze`,score ≥ 0.85 的 PII 必须 `anonymize` 后再送 LLM。
- **出口**:对 `result.rows` 文本字段调 `analyze`(可配置仅高敏字段)。

---

## C7. LangGraph → Cube

| 接口 | 路径 | 用途 |
|---|---|---|
| Meta | `GET /cubejs-api/v1/meta` | 拿可用 cubes/measures/dimensions |
| Load | `POST /cubejs-api/v1/load` | 用 Cube Query JSON 跑度量 |
| SQL | `POST /cubejs-api/v1/sql` | Cube 把 Query 翻译成 SQL(供我们审计) |

约束:
- LangGraph **优先用 Cube measures**;无匹配时降级到原始表 + 自然语言 SQL。
- 鉴权:JWT,token 由 langgraph-app 注入(包含 `user_id`/`role`,Cube 端做 RLS)。

---

## C8. LangGraph → DataHub

| 接口 | 路径 | 用途 |
|---|---|---|
| 检索 | `GET /openapi/v2/entity/dataset?query=...` | 查表/列、PII tag、业务术语 |
| Glossary | GraphQL `searchAcrossEntities(types:[GLOSSARY_TERM])` | 业务词典 → 列映射 |
| Lineage | GraphQL `dataset(urn:...).lineage` | 上下游影响分析 |

约束:
- 仅作为 **Schema Linking 的术语来源**,不做权限决策。
- DataHub 不可用时 LangGraph 必须降级(只用 Cube + pgvector),不阻断主流程。

---

## C9. LangGraph → pgvector

直连 PostgreSQL(`asyncpg`),Schema:
```sql
CREATE TABLE schema_chunks (
  id            uuid primary key,
  source        text not null,           -- 'cube'|'datahub'|'few_shot'|'table_desc'
  business_unit text,
  text          text not null,
  embedding     vector(1024),            -- bge-m3 维度
  metadata      jsonb,
  updated_at    timestamptz default now()
);
CREATE INDEX ON schema_chunks USING hnsw (embedding vector_cosine_ops);
```
查询契约(Python 函数):
```python
async def retrieve(question_emb: list[float], k: int = 20, filters: dict = {}) -> list[Chunk]
```

---

## C10. LangGraph → OPA

**Endpoint**:`POST http://opa:8181/v1/data/text2sql/allow`

```json
// 请求
{
  "input": {
    "user":   { "id": "alice@bank", "role": "RM", "business_unit": "CIB-APAC" },
    "action": "execute_sql",
    "tables": ["client","exposure"],
    "columns":["client.cif_id","exposure.exposure_amt"],
    "ops":    ["SELECT"],
    "estimated_cost": 1234
  }
}
// 响应
{
  "result": {
    "allow": true,
    "reasons": [],
    "obligations": { "row_filter": "rm_owner = 'alice@bank'" }
  }
}
```

- `allow=false` → 拒答,`reasons` 入 trace。
- `obligations.row_filter` → LangGraph 在 SQL 外层包 `WHERE`(双保险,Trino RLS 是首要)。

---

## C11. LangGraph → Trino

**Endpoint**:`POST http://trino:8081/v1/statement`

必填 Headers:
| Header | 值 |
|---|---|
| `X-Trino-User` | `alice@bank` |
| `X-Trino-Source` | `text2sql-langgraph` |
| `X-Trino-Catalog` | `pgvector_cib`(本试点) |
| `X-Trino-Schema` | `cib` |
| `X-Trino-Trace-Token` | `<trace_id>` |
| `X-Trino-Client-Tags` | `app=text2sql,role=RM` |

约束:
- 用户专属只读 catalog 账户,无 DDL/DML 权限
- 资源组 `text2sql_default`:max-mem 4GB,query timeout 60s
- 失败 → 返回 sqlState + 错误文本,LangGraph 进入 self-repair

---

## C12. LangGraph → Langfuse

通过 `langfuse` Python SDK(异步、批量)写入:
- 一个 `trace`(顶层),`name="text2sql.query"`,`user_id`,`session_id`
- 每个节点一个 `span`,记录 input/output/metadata
- 模型调用以 `generation` 形式记录(LiteLLM Callback 自动写,LangGraph 不重复)

约束:
- **不写 PII 原文**;仅写脱敏后内容
- `trace_id` 必须等同于 `X-Trace-Id`

---

## C13. LangGraph → Argilla

通过 `argilla` Python SDK 写入 `Dataset(name="text2sql_feedback")`:
```python
Record(
  id=trace_id,
  fields={
    "question": ..., "sql": ..., "result_preview": ..., "explanation": ...
  },
  metadata={
    "user_id": ..., "role": ..., "model": ..., "prompt_version": ...,
    "tables_used": [...], "cost_usd": ..., "latency_ms": ...
  },
  vectors={ "question": question_embedding },
  responses=[{ "thumb": "up|down", "corrected_sql": "..." }] # 用户提交后追加
)
```

---

## C14. 各服务 → OTel Collector

- 协议:OTLP gRPC `4317` / HTTP `4318`
- 标准属性:`service.name`、`service.version`、`deployment.environment`
- 自定义属性(强制):`trace_id`(=业务 trace_id)、`user.id`、`user.role`、`text2sql.node`(L5 内)

---

## C15. Prometheus 抓取 ← 各服务 `/metrics`

指标命名约定:`text2sql_<area>_<metric>{node="...",model="...",status="..."}`,如:
- `text2sql_node_latency_ms_bucket{node="sql_generate"}`
- `text2sql_sql_validation_failed_total{reason="missing_limit"}`
- `text2sql_llm_cost_usd_total{model="gpt-4o",route="sql_gen"}`
- `text2sql_eval_accuracy{set="golden_v1"}`

---

## 契约测试要求

| 边界 | 工具 | 何时跑 |
|---|---|---|
| C2/C12/C13 | Pydantic + JSON Schema 双向校验 | PR、CI |
| C4 | LiteLLM mock(VCR/Cassettes 录制) | PR、CI |
| C7/C8/C10/C11 | Testcontainers 拉真服务,跑 smoke contract | PR(夜间)、Release |
| C5/C6/C9 | Testcontainers + 固定模型版本 | PR(夜间)、Release |

详见 [`../testing/test-strategy.md`](../testing/test-strategy.md)。
