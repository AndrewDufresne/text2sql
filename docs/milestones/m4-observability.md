# Phase 4 — Observability & Operability 实施记录

> 对应 ADR-0006。L0/L1 治理层落地:LGTM 栈 + OTel SDK + Portainer。
> Backstage 与 MLflow 显式延后(非 Phase 4 关键路径)。

## 已实现(代码层)

| 模块 | 路径 | 状态 |
|---|---|---|
| Prometheus 指标库 + OTel 引导 | `services/langgraph-app/app/metrics.py` | ✅ |
| `GET /metrics` 端点 | `services/langgraph-app/app/main.py` | ✅ |
| 计数器接入(请求 / 安全拦截 / 自修复 / LLM / Feedback) | `app/graph.py`, `app/clients/litellm.py`, `app/main.py` | ✅ |
| FastAPI OTel 自动埋点 (best-effort) | `app/metrics.py::configure_otel` | ✅ |
| Pyproject 新增 5 个观测依赖 | `services/langgraph-app/pyproject.toml` | ✅ |
| 单测:4 个 metrics 用例 | `services/langgraph-app/tests/unit/test_metrics.py` | ✅ |
| Compose: 观测栈(LGTM + OTel) | `compose/70-observability.yml` | ✅ |
| Compose: 平台门户(Portainer) | `compose/80-portal.yml` | ✅ |
| Prometheus scrape + 告警规则 | `config/prometheus/{prometheus,rules}.yml` | ✅ |
| Alertmanager 路由 (dev-null) | `config/alertmanager/alertmanager.yml` | ✅ |
| Loki 单体配置 | `config/loki/loki-config.yml` | ✅ |
| Tempo 单体配置 (OTLP HTTP/gRPC) | `config/tempo/tempo-config.yml` | ✅ |
| OTel Collector pipeline (traces→Tempo, logs→Loki, metrics→Prom) | `config/otel-collector/otel-config.yml` | ✅ |
| Grafana provisioning(3 数据源 + dashboard 自动加载) | `config/grafana/provisioning/**` | ✅ |
| Grafana dashboard:t2sql/ai(9 卡片) | `config/grafana/dashboards/t2sql-ai.json` | ✅ |
| Make 目标:`up-obs` `down-obs` `up-portal` `up-all` `health-obs` | `Makefile`、`make.cmd` | ✅ |
| `.env` / `.env.example` 新增观测端口段 | — | ✅ |
| ADR-0006 | `docs/adr/0006-phase4-observability.md` | ✅ |

## 指标命名约定(L0 §7)

`text2sql_<area>_<metric>`:

| 名称 | 类型 | 标签 | 用途 |
|---|---|---|---|
| `text2sql_requests_total` | counter | status, error_code | 整体吞吐 + 失败结构 |
| `text2sql_request_latency_seconds` | histogram | — | P50/P95/P99 延迟(buckets 0.1-32s) |
| `text2sql_security_blocks_total` | counter | reason | PII / Injection / SQL_UNSAFE / OPA_DENIED |
| `text2sql_self_repair_total` | counter | — | 自修复触发次数 |
| `text2sql_llm_calls_total` | counter | purpose, outcome | sql_generate / explain × ok / error |
| `text2sql_feedback_total` | counter | sink, rating | argilla / local-jsonl × thumbs_up/down/correction |

## 数据流

```
langgraph-app /metrics (pull)            ┌────────────┐
   ──────────────────────────────────►   │ Prometheus │  ◄── Alertmanager
                                          └─────┬──────┘
langgraph-app OTel SDK (push, OTLP HTTP)        │
   ──► otel-collector ──► Tempo (traces)        │
                       └─► Loki   (logs)        │
                                                ▼
                                        ┌────────────┐
                                        │  Grafana   │  ◄── 浏览器
                                        │  3 datasources auto-provisioned
                                        │  Dashboard: t2sql/ai
                                        └────────────┘
```

OTel SDK 在 `OTEL_EXPORTER_OTLP_ENDPOINT` 未设时降级为 no-op,保证 venv / CI 单测无外部依赖。

## 一次性首跑步骤

```powershell
cd text2sql-platform

# 1) 复制 .env (如已存在,在末尾追加 Phase 4 段;`.env.example` 已是最新)
copy .env.example .env  # 或合并 Phase 4 段

# 2) 起观测栈(独立,可与 app 栈分别管理)
.\make.cmd up-obs

# 3) 重新构建 langgraph-app(注入 Phase 4 镜像 + OTEL_EXPORTER_OTLP_ENDPOINT)
.\make.cmd vendor
docker compose --env-file .env -f compose\00-network.yml -f compose\10-state.yml `
  -f compose\20-platform.yml -f compose\30-data.yml -f compose\40-capability.yml `
  -f compose\50-app.yml up -d --build langgraph-app

# 4) 健康检查
.\make.cmd health-obs

# 5) 浏览器
#    Prometheus  http://localhost:9090
#    Alertmanager http://localhost:9093
#    Grafana     http://localhost:3001  (admin / admin_dev_only;匿名 Viewer 也可见)
#    Portainer   http://localhost:9000  (首次访问需创建 admin)
#    Tempo API   http://localhost:3200
#    Loki API    http://localhost:3100
```

## 单测

```powershell
cd services\langgraph-app
..\..\.venv\Scripts\python.exe -m pytest -m "not e2e" -q
# 107 passed (含 Phase 4 新增 4 个 metrics 用例)
```

## 已验证(本地 Docker Compose)

| 验证项 | 命令 / 现象 |
|---|---|
| `/metrics` 暴露 6 个 `text2sql_*` 系列 | `curl http://localhost:8080/metrics` |
| Prometheus 抓到 `up{job="langgraph-app"}=1` | `/api/v1/query?query=up{job="langgraph-app"}` |
| 一次成功 query → counter +1 | `text2sql_requests_total{status="ok",error_code="none"} 1.0` |
| 一次成功 query → 两次 LLM 调用 | `text2sql_llm_calls_total{purpose="sql_generate"} 1.0` 与 `purpose="explain"` 各 1 |
| Tempo 收到 traces,`service.name=langgraph-app` | `/api/search?tags=service.name=langgraph-app` 返回非空 |
| Grafana 自动 provisioning 3 个 datasources + 1 个 dashboard `t2sql-ai` | `/api/datasources`, `/api/search?type=dash-db` |

## 显式延后(进入 backlog)

| 项目 | 原因 | 触发条件 |
|---|---|---|
| Backstage | Node 构建重、单租户场景 ROI 低 | 服务数量 ≥ 12 或多团队协作时 |
| Promtail / Docker loki driver | OTel logs pipeline 已铺好,先用 stdout + JSON;批量上线后再加 | 有日志检索需求时 |
| MLflow Model Registry | Langfuse Prompt Registry 已覆盖 prompt 版本;模型卡片场景未到 | Model Risk 团队入局 |
| Reranker / DataHub / Cube /meta | Phase 3 ADR 已显式 defer | 业务域 ≥ 2 时一并补 |
| Alertmanager 真实 receiver | dev 不需要 | 进入 SIT/UAT |

## 仍开放的问题(Architecture §10 子集)

- 行内 SSO/OAuth 接入(Grafana / Portainer 当前仅强密码)
- Loki 长期归档至 S3(目前本地 filesystem,7天滚)
- 行内 Prometheus 告警渠道(Slack / Teams / Email)
