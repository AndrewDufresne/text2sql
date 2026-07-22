# Text-to-SQL 企业级平台 — 顶层架构(Architecture)

> 版本:v0.1(草案,待评审)
> 适用范围:CIB(Corporate & Institutional Banking)Text-to-SQL 试点 → 平台化
> 部署形态:本机 Docker Compose(后续可迁 K8s)
> 试点数据域:CIB 客户 360(`client / account / exposure / transaction`)

---

## 1. 设计目标与约束

### 1.1 业务目标
- 让 RM、风险、合规、运营、Finance 等角色用**自然语言**安全、准确、可审计地查询 CIB 数据。
- 减少数据团队"取数工单",让分析自助化,同时不引入新的合规风险。

### 1.2 工程目标(SLO 草案,待与业务确认)
| 维度 | 目标 |
|---|---|
| Result Match(结果集等价) | MVP ≥ 85%,GA ≥ 95% |
| Schema Linking Recall@5 | ≥ 95% |
| 拒答精确率(越权/无答案) | ≥ 99% |
| 注入/越权拦截率 | 100%(硬指标) |
| P95 端到端延迟 | ≤ 8s |
| 单查询平均成本 | ≤ $0.02(云模型为主) |

### 1.3 非功能性约束(硬约束)
- **只读**:Text-to-SQL 仅生成 `SELECT`;任何 DDL/DML/系统函数一律拒绝。
- **身份穿透**:用户身份贯穿至执行层(Trino),由执行层做行/列权限。
- **可审计**:每个请求一个 `trace_id`,端到端落盘 ≥ 7 年(归档层)。
- **可替换**:每层模块通过显式契约暴露能力,任意一个可独立升级或替换。
- **TDD 驱动**:每个模块**先写测试**,后写实现;契约 + 单元 + 集成 + E2E + Eval 全覆盖。

---

## 2. 八层架构(分层视图)

```
┌────────────────────────────────────────────────────────────────────┐
│ L7 体验层  Chainlit(Web Chat)                                      │
├────────────────────────────────────────────────────────────────────┤
│ L6 HITL 层  Argilla(澄清 / 审批 / 反馈 / Golden Set 标注)         │
├────────────────────────────────────────────────────────────────────┤
│ L5 编排层  LangGraph(状态机:7 节点 + Self-Repair Loop)           │
├────────────────────────────────────────────────────────────────────┤
│ L4 能力层  LiteLLM Gateway · TEI(嵌入/重排) · Presidio(PII)      │
│            sqlglot(SQL AST 校验,以库形式嵌入 L5)                  │
├────────────────────────────────────────────────────────────────────┤
│ L3 知识层  Cube(语义层) · DataHub(目录/术语/血缘) · pgvector    │
├────────────────────────────────────────────────────────────────────┤
│ L2 执行层  Trino(只读副本 + 用户身份穿透 + 配额)                  │
├────────────────────────────────────────────────────────────────────┤
│ L1 平台层  Langfuse(Trace/Prompt/Eval) · MLflow(Model Registry)  │
│            OPA(策略) · OTel Collector · Promptfoo(CI Eval)       │
├────────────────────────────────────────────────────────────────────┤
│ L0 治理层  Prometheus + Grafana + Loki + Tempo + Alertmanager      │
│            Portainer(容器) · Backstage(开发者门户,Phase 4)       │
└────────────────────────────────────────────────────────────────────┘
```

各层详细设计见 [`layers/`](./layers/) 子文档。

---

## 3. 数据流(Happy Path)

```
User
 │ 1. POST /api/query  (question + user_id + role)
 ▼
Chainlit ──► LangGraph App (FastAPI)
                │
                │ 2. PII 检测(Presidio)
                │ 3. Intent + Guardrails(NeMo / 自实现规则)
                │ 4. Schema Linking
                │     ├─ Cube /meta(度量/维度)
                │     ├─ DataHub Glossary(术语)
                │     └─ pgvector(历史 Q&A + 表/列描述向量)
                │ 5. SQL 生成(LiteLLM → 云模型 / Ollama 兜底)
                │ 6. SQL 校验(sqlglot AST)
                │ 7. OPA 授权(tables × user_role)
                │ 8. Dry-run(Trino EXPLAIN)
                │ 9. 执行(Trino,X-Trino-User=alice)
                │ 10. 结果脱敏(Presidio)
                │ 11. NL 解释(LiteLLM)
                ▼
              Response(SQL + rows + explanation + trace_id)
                │
                ├─► Langfuse(全链路 trace + token + cost)
                ├─► Loki(结构化日志)
                ├─► Tempo(OTel 分布式 trace)
                └─► Argilla(👍/👎/修正 SQL → Golden Set 候选)
```

---

## 4. 跨层 I/O 契约(总览)

完整契约见 [`contracts/io-contracts.md`](./contracts/io-contracts.md)。摘要:

| # | 边界 | 协议 | 关键字段 |
|---|---|---|---|
| C1 | Browser → Chainlit | HTTP/WS | question, session_id |
| C2 | Chainlit → LangGraph | HTTP `POST /api/query` | trace_id, user_id, role, question |
| C3 | LangGraph 节点间 | Pydantic `GraphState` | trace_id, current_node, errors[], spans[] |
| C4 | LangGraph → LiteLLM | OpenAI 兼容 `/v1/chat/completions` | + `metadata.trace_id`、`metadata.session_id` |
| C5 | LangGraph → TEI | HTTP `/embed`、`/rerank` | inputs[] |
| C6 | LangGraph → Presidio | HTTP `/analyze`、`/anonymize` | text, language |
| C7 | LangGraph → Cube | HTTP `/cubejs-api/v1/{meta,sql,load}` | query JSON |
| C8 | LangGraph → DataHub | GraphQL/OpenAPI `/api/v2/...` | urn 检索 |
| C9 | LangGraph → pgvector | SQL(asyncpg) | embedding 检索 |
| C10 | LangGraph → OPA | HTTP `POST /v1/data/text2sql/allow` | input.{user,role,tables,ops} |
| C11 | LangGraph → Trino | HTTP `POST /v1/statement` | + `X-Trino-User`, `X-Trino-Source`, `X-Trino-Trace-Token` |
| C12 | LangGraph → Langfuse | SDK(HTTP) | trace + spans + generations |
| C13 | LangGraph → Argilla | SDK(HTTP) | feedback record |
| C14 | OTel SDK → Collector | OTLP gRPC/HTTP | spans, metrics, logs |
| C15 | Prom Scrape ← 各 service `/metrics` | HTTP | Prometheus exposition |

> **强制**:任何跨层调用都必须携带 `trace_id`(HTTP header `X-Trace-Id`),由 LangGraph 入口生成,贯穿全链路。

---

## 5. 部署拓扑(本机 Compose)

### 5.1 Compose 文件分层
```
compose/
├── 00-network.yml          # 共享 docker network: t2sql-net
├── 10-state.yml            # postgres / redis / clickhouse / minio / elasticsearch / pgvector
├── 20-platform.yml         # litellm / langfuse(+worker) / mlflow / opa / otel-collector
├── 30-data.yml             # cube / trino
├── 31-datahub.yml          # datahub quickstart 一组(可独立 up/down)
├── 40-capability.yml       # presidio-analyzer / -anonymizer / tei(embed) / tei(rerank) / ollama
├── 50-app.yml              # langgraph-app / chainlit-ui
├── 60-hitl.yml             # argilla-quickstart
├── 70-observability.yml    # prometheus / grafana / loki / tempo / alertmanager
└── 80-portal.yml           # portainer (Phase 4: + backstage)
```
启动:
```powershell
docker compose -f compose/00-network.yml -f compose/10-state.yml ... up -d
```
建议用 `Makefile` 或 `tasks.json` 封装组合命令。

### 5.2 端口约定(本机)
| 服务 | 端口 | 用途 |
|---|---|---|
| Chainlit | 8000 | Web UI |
| LangGraph App(FastAPI) | 8080 | API + `/metrics` + `/healthz` |
| LiteLLM | 4000 | OpenAI 兼容代理 |
| Langfuse Web | 3000 | Trace UI |
| Cube | 4000(冲突→4040) | Cube API + Playground |
| Trino | 8081 | Query coordinator |
| DataHub Frontend | 9002 | UI |
| Argilla | 6900 | UI + API |
| pgvector(PG) | 5433 | 业务样例 + 向量库 |
| Postgres(平台元数据) | 5432 | Langfuse/MLflow/Cube 元数据 |
| Grafana | 3001 | 大盘 |
| Prometheus | 9090 | — |
| Portainer | 9000 | 容器管理 |
| Ollama | 11434 | 本地模型 |
| TEI Embed | 8082 | 嵌入 |
| TEI Rerank | 8083 | 重排 |
| Presidio Analyzer | 5001 | — |
| Presidio Anonymizer | 5002 | — |
| OPA | 8181 | 策略 |
| OTel Collector | 4317(gRPC) / 4318(HTTP) | 接收 OTLP |

> 端口冲突最终方案在 `docker-compose` 的 `ports` 映射处统一处理,本文档为约定。

### 5.3 GPU 资源切分(8-12GB 显存约束)
| 容器 | 显存预算 | 备注 |
|---|---|---|
| Ollama(qwen2.5:7b-q4) | ~5 GB | SQL 生成兜底 / Eval 基线 |
| TEI(bge-m3 嵌入) | ~2 GB | 检索主力 |
| TEI(bge-reranker-v2-m3) | ~2 GB | 与嵌入分两实例,显存紧张时退到 CPU |
| 总计 | ≤ 9 GB | 留 buffer 给系统 |

> 若同时拉起会 OOM,**默认仅启嵌入 + Ollama**;Reranker 按需启动。

---

## 6. 安全与合规(从 Day 1 强制)

| # | 风险 | 控制 | 落点 |
|---|---|---|---|
| S1 | SQL 越权/破坏 | sqlglot AST 白名单 + 只读账号 + 强制 LIMIT | L4 / L2 |
| S2 | 行/列权限 | Trino + 受限视图(后期接 Ranger) | L2 |
| S3 | PII 入/出双向脱敏 | Presidio | L4 |
| S4 | Prompt Injection | NeMo Guardrails 规则 + 输入分类器 | L4 / L5 |
| S5 | 模型/提示版本管控 | Langfuse Prompt Registry + Git PR | L1 |
| S6 | 模型出公网 | 仅 LiteLLM 一条出网链路;`.env` 里 key | L4 |
| S7 | 全链路审计 | Langfuse(7天热)+ ClickHouse 归档 + Loki | L1 / L0 |
| S8 | 策略即代码 | OPA `text2sql` package | L1 |
| S9 | 密钥管理 | Phase 1 `.env`;Phase 4 Vault | L0 |

---

## 7. 测试驱动(TDD)总策略

> 详见 [`testing/test-strategy.md`](./testing/test-strategy.md)。

七层测试金字塔(自下而上):
1. **契约测试**:Pydantic schema + JSON Schema + Pact(节点间)
2. **单元测试**:每节点逻辑(mock 外部依赖)
3. **集成测试**:Testcontainers 拉真实 PG/Trino/LiteLLM(mock 上游模型)
4. **E2E 测试**:docker compose 起最小栈,跑 happy path + 关键失败路径
5. **Eval 测试**:Promptfoo + Golden Set,CI 阻断阈值
6. **安全测试**:注入/越权/PII 红队用例,100% 必拦
7. **可观测测试**:trace 完整性、metric 暴露、log 字段

**强制**:任何 PR 必须先有失败测试,再补实现。无测试 = 不合并。

---

## 8. 分阶段实施

| Phase | 周 | 目标 | 完成标准 |
|---|---|---|---|
| **P1 最小闭环** | W1-W2 | 状态服务 + LiteLLM + Langfuse + Trino + Cube + LangGraph + Chainlit + DataHub | 1 个问题→SQL→结果→trace 完整 |
| **P2 RAG + 安全** | W3-W4 | pgvector + TEI + Presidio + sqlglot + OPA | 注入拦截 100%,Recall@5 ≥ 90% |
| **P3 HITL + Eval** | W5-W6 | Argilla + Promptfoo CI | 反馈→Golden Set→CI 阻断闭环 |
| **P4 可观测 + 门户** | W7-W8 | Prom/Grafana/Loki/Tempo + Portainer + (Backstage 延后) + (MLflow 延后) | 在线:`t2sql/ai` Dashboard + 6 个 `text2sql_*` 指标 + Tempo 距踪 + Portainer。实现记录见 [`PHASE4.md`](./PHASE4.md)、ADR-0006。 |

---

## 9. 模块清单(对应已下载镜像)

| 模块 | 镜像 | 子架构文档 |
|---|---|---|
| LangGraph App | 自建 from `python:3.11-slim` | [L5](./layers/L5-orchestration.md) |
| Chainlit UI | 自建 from `python:3.11-slim` | [L7](./layers/L7-experience.md) |
| Argilla | `argilla/argilla-quickstart:latest` | [L6](./layers/L6-hitl.md) |
| LiteLLM | `ghcr.io/berriai/litellm:main-latest` | [L4](./layers/L4-capability.md) |
| Ollama | `ollama/ollama:latest` | [L4](./layers/L4-capability.md) |
| TEI | `ghcr.io/huggingface/text-embeddings-inference:cpu-latest` | [L4](./layers/L4-capability.md) |
| Presidio | `mcr.microsoft.com/presidio-analyzer/-anonymizer` | [L4](./layers/L4-capability.md) |
| Cube | `cubejs/cube:latest` | [L3](./layers/L3-knowledge.md) |
| pgvector | `pgvector/pgvector:pg16` | [L3](./layers/L3-knowledge.md) |
| DataHub | `acryldata/datahub-*` + Kafka/ES/MySQL | [L3](./layers/L3-knowledge.md) |
| Trino | `trinodb/trino:latest` | [L2](./layers/L2-execution.md) |
| Langfuse | `langfuse/langfuse:3` + worker | [L1](./layers/L1-platform.md) |
| MLflow | `ghcr.io/mlflow/mlflow:latest` | [L1](./layers/L1-platform.md) |
| OPA | `openpolicyagent/opa:latest-rootless` | [L1](./layers/L1-platform.md) |
| OTel Collector | `otel/opentelemetry-collector-contrib:latest` | [L1](./layers/L1-platform.md) |
| Promptfoo | `ghcr.io/promptfoo/promptfoo:latest` | [L1](./layers/L1-platform.md) |
| Prom/Grafana/Loki/Tempo/Alertmanager | 各官方镜像 | [L0](./layers/L0-governance.md) |
| Portainer | `portainer/portainer-ce:latest` | [L0](./layers/L0-governance.md) |
| Backstage(P4) | 自建 from `node:20-alpine` | [L0](./layers/L0-governance.md) |

---

## 10. 待确认事项(请评审时回答)

| # | 问题 | 影响 |
|---|---|---|
| Q1 | RM/分析师试点用户名单与 SSO/IdP 接入方式 | 身份穿透实现细节 |
| Q2 | 行内云模型可选清单(Azure OpenAI? 行内自建网关?) | LiteLLM 路由配置 |
| Q3 | 试点数据落地路径:用合成数据还是脱敏副本? | pgvector 同库样例数据生成方式 |
| Q4 | Model Risk / Compliance 模板与审批流 | MLflow Model Card 字段 |
| Q5 | 审计归档 7 年的目标存储(S3 兼容?对象锁?) | ClickHouse → 归档管道 |

---

## 11. 文档导航

- 子架构(每层):[`layers/`](./layers/)
- I/O 契约总表:[`contracts/io-contracts.md`](./contracts/io-contracts.md)
- 测试策略:[`testing/test-strategy.md`](./testing/test-strategy.md)
