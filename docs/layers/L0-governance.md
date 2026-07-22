# L0 — 治理层(Governance & Operability)

> 七个组件:**Prometheus · Grafana · Loki · Tempo · Alertmanager**(LGTM 栈)· **Portainer**(容器管理)· **Backstage**(开发者门户,Phase 4)

---

## 1. 模块映射

| 模块 | 镜像 | 端口 | 角色 |
|---|---|---|---|
| Prometheus | `prom/prometheus:latest` | 9090 | 指标抓取 + 规则告警 |
| Alertmanager | `prom/alertmanager:latest` | 9093 | 告警路由(Email/Slack/Teams) |
| Loki | `grafana/loki:latest` | 3100 | 日志聚合 |
| Tempo | `grafana/tempo:latest` | 3200 | 分布式 trace |
| Grafana | `grafana/grafana:latest` | 3001 | 统一可视化 |
| Portainer | `portainer/portainer-ce:latest` | 9000 | 容器/Compose 管理 |
| Backstage(P4) | 自建 from `node:20-alpine` | 7007 | 服务目录 + TechDocs + Scaffolder |

---

## 2. 数据流(可观测三件套)

```
各服务 ──(OTel SDK / exposition)──► OTel Collector ──┬──► Tempo (traces)
                                                     ├──► Prom (metrics)
                                                     └──► Loki (logs)
                                          Prometheus ──► Alertmanager ──► Email/Teams
                                          Grafana ──► 三者 + Langfuse(iframe)
```

---

## 3. Grafana Dashboard(四个角色面板)

| 角色 | 面板 | 关键卡片 |
|---|---|---|
| **业务/产品** | `t2sql/business` | 采纳率、👍率、TOP 问题、节省工单数、ROI 曲线、各 BU 准确率热力 |
| **数据治理** | `t2sql/data` | Schema 漂移告警、术语覆盖率、口径冲突、待审视图 |
| **AI 工程** | `t2sql/ai` | Result Match、Recall@K、self-repair 触发率、Prompt Diff、Shadow vs Canary、失败模式 TOP |
| **风控/合规** | `t2sql/risk` | Guardrail 命中、越权拒绝、Model Card 到期、审计抽样 |

> Phase 1 仅 `t2sql/ai` + 基础设施;其他在 Phase 4 完整。

---

## 4. 告警规则(`config/prometheus/rules.yml` 草案)

| 告警 | 表达式(伪) | 严重度 |
|---|---|---|
| `Text2SqlAccuracyDrop` | `text2sql_eval_accuracy{set="golden_v1"} < 0.85 for 1h` | P1 |
| `Text2SqlInjectionLeak` | `increase(text2sql_security_injection_passed_total[5m]) > 0` | P0 |
| `Text2SqlP95Slow` | `histogram_quantile(0.95, text2sql_request_latency_ms_bucket) > 8000 for 10m` | P2 |
| `Text2SqlCostSpike` | `rate(text2sql_llm_cost_usd_total[1h]) > $10` | P2 |
| `Text2SqlServiceDown` | `up{job=~"langgraph-app|litellm|trino|cube"} == 0` | P1 |
| `OPAUnreachable` | `up{job="opa"} == 0` | P0(fail-closed,但仍告警) |

---

## 5. Portainer

- 接管所有 compose stack
- 用户:`admin`(平台)、`viewer`(只读,给业务/合规)
- 用 **Stacks** 模式注册 `compose/*.yml`,可视化启停
- 限制:**禁修改 `litellm` 容器的 ENV**(避免误改 key 路由)

---

## 6. Backstage(Phase 4,门户)

### 6.1 Catalog(`catalog-info.yaml` 注册物)
- `Component`:langgraph-app, chainlit-ui, litellm, cube, trino, langfuse, argilla, datahub, presidio, opa
- `System`:`text2sql-platform`(承载所有 Component)
- `API`:8 个跨层契约(C2/C4/C7/C10/C11 等),关联 OpenAPI/JSON Schema
- `Resource`:pgvector, MinIO, ES, ClickHouse
- `Domain`:`cib-customer360`(业务域)

### 6.2 插件(社区/自研)
- TechDocs(每个 Component README/ADR 自动渲染)
- Kubernetes / Docker(展示运行状态)
- Grafana / Prometheus(嵌入图表)
- 自研:Langfuse 卡片、Argilla 待审计数、Promptfoo 最近评估结果

### 6.3 Scaffolder 模板
- "新增业务域到 Text2SQL":输入 `domain_name` → 一次性建 PR:
  - `config/cube/schema/<domain>/`
  - `config/opa/data/<domain>.json`
  - `evals/golden_set/<domain>_v1.yaml`
  - `data/seeds/<domain>/*.sql`
  - DataHub Glossary 模板
  - Argilla workspace 创建脚本

---

## 7. 输入输出约束

- **指标**:服务必须暴露 `/metrics`(Prom 格式),命名遵守 `text2sql_<area>_<metric>` 约定
- **日志**:JSON,字段必含 `ts, level, service, trace_id, user_id?, msg`,经 OTel Collector 走 Loki
- **Trace**:OTLP,Span name 用 `text2sql.<node>` 或 `<component>.<op>`
- **告警**:每条告警必须有 Runbook 链接(指向 `docs/runbooks/<alert>.md`)
- **Backstage**:每个 Component 必须有 Owner、Lifecycle、SLO 字段

---

## 8. 安全约束

- Grafana / Portainer / Backstage 后台 → SSO(Phase 2);Phase 1 强密码 + 内网
- Loki 日志中禁出现 PII 原文(由 OTel Collector `attributes/redact` 强制)
- Backstage Scaffolder 仅在 PR 中提议改动,不直接 merge

---

## 9. 测试策略

### 契约
- 每服务 `/metrics` 必含约定指标(用 `pytest` + `prometheus_client.parser`)
- Backstage `catalog-info.yaml` schema 校验

### 单元
- 告警规则(Prom `promtool test rules`)

### 集成
- 一次 E2E 请求:在 Tempo 能按 trace_id 检索,在 Loki 能按 trace_id 过滤,在 Prom 能查到对应指标变化
- 触发 `Text2SqlInjectionLeak` 模拟 → Alertmanager 收到

### 安全
- 注入用例的日志中**不含 PII**

### 可观测(自我验证)
- Grafana Dashboard JSON 在 CI 中用 `grafonnet` 或 dashboard linter 校验

---

## 10. 待确认

- Alert 通知渠道(Email/Teams/Slack)与 oncall 排班
- Backstage 是否托管到行内 IDP 之下
- Loki/Tempo 保留期(30 天热,长期归档到对象存储?)
- Phase 1 是否先用 Langfuse 自带 UI 替代 Grafana AI 面板,后期再合并
