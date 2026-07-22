# L5 — 编排层(Orchestration)

> 唯一组件:**LangGraph App**(`python:3.11-slim` + FastAPI + LangGraph)
> 端口:`8080`(API),`9100`(Prom `/metrics`)

---

## 1. 模块职责

- 把一次用户提问转化为一条**可观测、可审计、可恢复**的状态机执行
- 将 L4(能力)、L3(知识)、L2(执行)、L1(平台)能力**编排**为业务流程
- 提供 HTTP API:`/api/v1/query`、`/api/v1/feedback`、`/api/v1/approval/callback`、`/healthz`、`/metrics`

---

## 2. 状态机

```
                     ┌────────────────┐
                     │  pii_guard      │ Presidio(入)
                     └───────┬────────┘
                             ▼
                     ┌────────────────┐
                     │  intent_guard   │ NeMo Rules + 分类
                     └───────┬────────┘
              clarify? ◄─────┴─────► continue
                ▼                       ▼
         ┌─────────────┐         ┌──────────────┐
         │ clarify     │         │ schema_link  │ Cube/DataHub/pgvector+TEI
         └─────────────┘         └──────┬───────┘
                                        ▼
                                ┌──────────────┐
                                │ sql_generate │ LiteLLM(云) / Ollama 兜底
                                └──────┬───────┘
                                        ▼
                                ┌──────────────┐
                                │ sql_validate │ sqlglot AST + 规则
                                └──────┬───────┘
                                        ▼
                                ┌──────────────┐
                                │ opa_check    │ OPA
                                └──────┬───────┘
                                        ▼
                                ┌──────────────┐
                                │ dry_run       │ Trino EXPLAIN
                                └──────┬───────┘
                          high cost? ◄─┴─► ok
                              ▼            ▼
                       ┌────────────┐  ┌─────────┐
                       │ approval   │  │ execute │ Trino
                       │(异步,L6) │  └────┬────┘
                       └────┬───────┘        ▼
                            └────────► ┌──────────────┐
                                       │ pii_guard(出)│
                                       └──────┬───────┘
                                              ▼
                                       ┌──────────────┐
                                       │ explain      │ LiteLLM
                                       └──────┬───────┘
                                              ▼
                                       ┌──────────────┐
                                       │ emit         │ Langfuse + Argilla + OTel
                                       └──────────────┘
            self_repair(N≤2)  ◄────── execute 失败 ──── sql_generate
```

---

## 3. 节点契约

所有节点签名相同:

```python
async def node(state: GraphState) -> GraphState
```

`GraphState` 详见 [contracts/io-contracts.md#c3](../contracts/io-contracts.md#c3-langgraph-节点间进程内)。

| 节点 | 读 | 写 | 失败行为 |
|---|---|---|---|
| `pii_guard` | request.question | pii_findings, request.question(脱敏) | 仅记录,不阻断 |
| `intent_guard` | request.question | intent, blocked? | block→`refused` |
| `clarify` | intent | needs_clarify=True | 返回 `need_clarify` |
| `schema_link` | request.question | schema_link.{tables,columns,metrics,recall} | recall<阈值→拒答 |
| `sql_generate` | + schema_link | sql_draft, model, prompt_ver | 重试 ≤2(self_repair) |
| `sql_validate` | sql_draft | sql_validated{safe,sql,violations,tables_used} | safe=False→`refused` |
| `opa_check` | sql_validated.tables_used | opa_decision | allow=False→`refused` |
| `dry_run` | sql_validated.sql | explain_plan{est_rows,est_cost} | cost>阈值→`approval` |
| `execute` | sql_validated.sql | execution{rows,row_count,truncated,error} | error→self_repair |
| `pii_guard(out)` | execution.rows | execution.rows(脱敏) | — |
| `explain` | sql,rows | explanation | 失败→空 |
| `emit` | * | spans→Langfuse, record→Argilla, metrics | — |

---

## 4. API 端点

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/v1/query` | POST | 见 [C2](../contracts/io-contracts.md#c2-chainlit--langgraph-app) |
| `/api/v1/feedback` | POST | `{trace_id, thumb, corrected_sql?, failure_mode?}` → Argilla |
| `/api/v1/approval/callback` | POST | Argilla webhook → 唤醒挂起的 graph |
| `/healthz` | GET | liveness;依赖检测看 `/readyz` |
| `/readyz` | GET | 检查 LiteLLM/Trino/OPA/Cube/Presidio/TEI 可达 |
| `/metrics` | GET | Prometheus exposition |

---

## 5. 配置(`config/langgraph-app/*.yaml`)

```yaml
limits:
  row_limit_default: 1000
  dry_run_cost_warn: 5_000_000     # rows
  dry_run_cost_block: 50_000_000
  self_repair_max: 2
  request_timeout_s: 60

routing:
  sql_generate:
    primary:  "litellm:router/sql-gen"
    fallback: "litellm:ollama/qwen2.5-7b"
  explain:
    primary:  "litellm:router/general-small"

prompts:
  sql_generate: "prompts/sql_generate@v1"   # Langfuse Prompt Registry
  explain:      "prompts/explain@v1"

features:
  presidio_in:  true
  presidio_out: true
  opa:          true
  reranker:     false                       # 显存紧张默认关
  cube:         true
  datahub:      true
```

---

## 6. 输入输出约束(关键)

- 入口必须生成 `trace_id`(UUIDv7),贯穿所有下游 HTTP/SDK 调用
- 出口必须包含:`status`、`trace_id`、(成功时)`sql / result / explanation / model / prompt_version / cost_usd / latency_ms`
- **不允许**直接调云模型;一律通过 LiteLLM
- **不允许**绕过 sqlglot 直接执行 SQL
- **不允许**绕过 OPA 决定权限
- 任何异常 → 必须落 `errors[]` 并 emit Langfuse span 状态 `error`

---

## 7. 测试策略

### 契约
- `GraphState` Pydantic 序列化往返
- 每节点的 input/output 字段最小集

### 单元
- 每节点独立测试(其他节点 mock):
  - `sql_validate` 用 50 个 SQL 样本(含 DDL/无 LIMIT/合法/越权表)
  - `opa_check` mock OPA 响应
  - self_repair 触发条件

### 集成
- Testcontainers 拉 PG/Trino/OPA/Presidio/TEI/LiteLLM(mock)
- 跑 happy path + 4 个失败分支

### E2E
- compose 起 P1 全栈:Chainlit → LangGraph → 全链路

### Eval
- Promptfoo 仅断言 LangGraph `/api/v1/query` 输出(不直接调 LiteLLM)

### 安全
- 红队用例集成到 `/api/v1/query`,断言 `status ∈ {refused}` 与 violations 列表

### 可观测
- 一次请求:Langfuse 1 trace + ≥7 spans;Tempo 跨 ≥3 服务;`/metrics` 出现节点级指标

---

## 8. 待确认

- 异步 approval 的实现:LangGraph checkpoint(Postgres) vs 业务侧 polling?
- self_repair 是否需要把上次错误结构化喂回(而非只贴报错文本)?
- 是否需要"无答案"主动检测(LLM 返回空 → 直接拒答而不是空 SQL)?
