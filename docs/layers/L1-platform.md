# L1 — 平台层(Platform)

> 五个组件:**Langfuse**(Trace/Prompt/Eval)· **MLflow**(Model Registry)· **OPA**(策略)· **OTel Collector**(遥测)· **Promptfoo**(CI Eval)

---

## 1. 模块映射

| 模块 | 镜像 | 端口 | 角色 |
|---|---|---|---|
| Langfuse Web | `langfuse/langfuse:3` | 3000 | Trace/Prompt/Dataset/Eval UI + API |
| Langfuse Worker | `langfuse/langfuse-worker:3` | — | 异步 ingest |
| MLflow | `ghcr.io/mlflow/mlflow:latest` | 5000 | Model Card / 版本登记(MinIO 作 artifact store) |
| OPA | `openpolicyagent/opa:latest-rootless` | 8181 | text2sql 授权策略 |
| OTel Collector | `otel/opentelemetry-collector-contrib:latest` | 4317/4318 | 接收并分发 traces/metrics/logs |
| Promptfoo | `ghcr.io/promptfoo/promptfoo:latest` | — | CI 中跑评估;不常驻 |

---

## 2. Langfuse(核心)

### 2.1 状态依赖
- Postgres(平台元数据库,5432)
- ClickHouse(trace 数据,24.12)
- Redis(队列)
- MinIO(blob,如长 prompt/result 截图)

### 2.2 输入输出
- **写入**:LangGraph SDK + LiteLLM Callback
  - 1 trace / 请求
  - ≥ 7 spans / trace(每节点一个)
  - 每次 LLM 调用 1 generation(LiteLLM 自动)
- **Prompt Registry**:`prompts/sql_generate@v1` 等,通过 SDK 拉取
- **Datasets**:Golden Set 双写(Argilla 主、Langfuse 镜像便于 UI 上做 LLM-as-judge)
- **不写 PII 原文**(同 [L6](./L6-hitl.md))

### 2.3 接口约束
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 由 `.env` 注入
- LiteLLM 配 `callbacks: ["langfuse"]`,LangGraph 用 `langfuse-python`
- `trace.user_id` = `request.user.id`,`session_id` = Chainlit session

---

## 3. MLflow

### 3.1 用法
- 登记**模型版本**:Ollama 拉的本地模型 + 云模型 alias(用 ModelVersion + 自定义 tags)
- **Model Card**:每个生产用模型一份(yaml/markdown artifact),含:owner、用途、风险等级、评估结果链接、监控告警阈值

### 3.2 输入输出
- HTTP 5000;后端 PG + MinIO(artifact)
- LangGraph 启动时拉取 "active" 模型 alias,记入 `metadata.model_version`

> Phase 1 仅做登记;Phase 4 接入正式 MRM 流程

---

## 4. OPA(text2sql 策略)

### 4.1 策略包(`config/opa/policies/text2sql.rego` 设计意图)
```
package text2sql

default allow = false

allow {
  input.action == "execute_sql"
  input.ops == ["SELECT"]
  every t in input.tables { t in data.allowed_tables[input.user.role] }
  every c in input.columns { c in data.allowed_columns[input.user.role] }
  input.estimated_cost < data.cost_limits[input.user.role]
}

obligations.row_filter = data.rls[input.user.role][input.user.id]
```
- `data.allowed_tables/columns/cost_limits/rls` 由 ConfigMap-style JSON 注入(`data.json`)
- 所有变更走 Git PR + CI 单测(rego unit test)

### 4.2 输入输出(C10)
- Request: `{user, action, tables, columns, ops, estimated_cost}`
- Response: `{allow, reasons[], obligations{row_filter?}}`

### 4.3 约束
- LangGraph 必须在 `sql_validate` 之后、`execute` 之前调用
- OPA 不可用 → fail-closed(拒答)

---

## 5. OTel Collector

### 5.1 Pipeline(`config/otel/collector.yaml` 草案)
```yaml
receivers:
  otlp: { protocols: { grpc: {}, http: {} } }
processors:
  batch: {}
  attributes/redact:
    actions:
      - key: pii.original
        action: delete
exporters:
  loki:    { endpoint: http://loki:3100/loki/api/v1/push }
  prometheus: { endpoint: 0.0.0.0:8889 }
  otlp/tempo: { endpoint: tempo:4317, tls: { insecure: true } }
service:
  pipelines:
    traces:  { receivers: [otlp], processors: [batch], exporters: [otlp/tempo] }
    metrics: { receivers: [otlp], processors: [batch], exporters: [prometheus] }
    logs:    { receivers: [otlp], processors: [batch, attributes/redact], exporters: [loki] }
```

### 5.2 约束
- 强制属性:`service.name`、`trace_id`(业务级)、`user.id`(脱敏)、`text2sql.node`
- 任何含 `pii.*` 属性的字段在 collector 层 drop

---

## 6. Promptfoo(CI Eval)

### 6.1 配置(`evals/promptfoo/promptfooconfig.yaml` 设计意图)
- providers:LangGraph App(`http://langgraph-app:8080/api/v1/query`),不是直接打 LLM
- tests:`evals/golden_set/cib_customer360_v1.yaml`、`adversarial_v1.yaml`
- 自定义 assertion `exec_sql_match`:对 LangGraph 返回的 `result.rows` 做 hash 比对

### 6.2 触发与门禁
- PR 改动 prompts/ / nodes/ / config/cube|opa → 自动触发
- 阈值见 [测试策略](../testing/test-strategy.md#layer-5--evalllm-质量)
- 报告 `npx promptfoo share` → 评论到 PR

---

## 7. 跨模块约束(L1 内部)

- `trace_id` 在 Langfuse / Tempo / Loki / Prom exemplar 中**完全一致**(必须能跨工具 join)
- OPA 决策日志通过 OTel 外发(便于审计)
- MLflow 与 Langfuse 中"模型版本"字段名统一(`model_version`)

---

## 8. 测试策略

### 契约
- Langfuse SDK 调用封装的 schema
- OPA `/v1/data/.../allow` request/response

### 单元
- OPA Rego 单测:每个 role × table 组合 ≥ 1 用例
- Promptfoo 自定义 `exec_sql_match` 函数

### 集成
- Testcontainers:Langfuse(精简版 PG/CH)+ OPA + LangGraph
- 一次请求后 → Langfuse trace 可被 SDK 读回

### Eval
- Promptfoo 自身在 CI 跑通 → 阈值检查

### 安全
- OPA 默认拒(无 policy 命中)→ fail-closed 验证

### 可观测
- Tempo 中按业务 trace_id 能搜出跨服务 span
- Prometheus 暴露 `text2sql_*` 指标完整

---

## 9. 待确认

- Langfuse v3 ClickHouse 资源占用是否本机可承受(初始评估约 2-4GB 内存)
- MLflow artifact 是否与 Langfuse 共用一套 MinIO bucket
- OPA `data.json` 由谁维护(数据治理 + 业务联合)
- Promptfoo 在 CI 调云模型的预算守门员(避免暴跑)
