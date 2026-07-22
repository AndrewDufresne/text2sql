# L2 — 执行层(Execution)

> 唯一组件:**Trino**(`trinodb/trino:latest`)
> 端口:`8081`
> 试点 Catalog:`pgvector_cib`(指向 L3 的 pgvector 业务样例库)

---

## 1. 模块职责

- 唯一的查询执行入口(LangGraph 不直连 PG)
- 用户身份穿透 + 资源隔离 + 配额 + 审计
- 多源查询(后续可加 Hive/Iceberg/Snowflake catalog,Phase 1 仅 PG)

---

## 2. 配置

### 2.1 Catalogs(`config/trino/catalog/*.properties`)
```
# pgvector_cib.properties
connector.name=postgresql
connection-url=jdbc:postgresql://pgvector:5432/cib
connection-user=trino_ro
connection-password=${TRINO_PG_RO_PASSWORD}
allow-drop-table=false
```

### 2.2 Resource Groups(`config/trino/resource-groups.json`)
```json
{
  "rootGroups": [{
    "name": "text2sql_default",
    "softMemoryLimit": "4GB",
    "hardConcurrencyLimit": 20,
    "maxQueued": 50
  }],
  "selectors": [{ "source": "text2sql-langgraph", "group": "text2sql_default" }]
}
```

### 2.3 全局限制(`config/trino/config.properties` 摘要)
- `query.max-execution-time=60s`
- `query.max-memory-per-node=2GB`
- `query.max-scan-physical-bytes=50GB`

---

## 3. 输入输出约束(C11)

### 3.1 必填 Headers
| Header | 说明 |
|---|---|
| `X-Trino-User` | 业务用户名(身份穿透) |
| `X-Trino-Source` | `text2sql-langgraph` |
| `X-Trino-Catalog` / `-Schema` | `pgvector_cib` / `cib` |
| `X-Trino-Trace-Token` | LangGraph 的 `trace_id` |
| `X-Trino-Client-Tags` | `app=text2sql,role=RM,bu=CIB-APAC` |

### 3.2 必拒
- 任何 DDL/DML(配置上 connector 已只读)
- 超时 60s
- 超内存 / 超扫描量

### 3.3 必返
- 行结果 + `row_count` + 是否截断
- `query_id`(用于审计与查询追踪)
- 错误时:`sqlState`、`errorCode`、`errorMessage`

---

## 4. 安全约束

- DB 账号 `trino_ro`:`SELECT` only,无 schema 修改权
- 应用层(LangGraph)再做一遍 `LIMIT` 注入 + sqlglot 校验(Defense in depth)
- Phase 2 加 **Apache Ranger**:列级脱敏 + 行级 RLS(替代/加强 Cube `securityContext`)
- Trino 访问审计:`event-listener` 把 `QueryCompleted` 推到 OTel/Loki
  - 每条 query 必记:`user, source, query_text(脱敏), state, queued/elapsed/cpu/peak_mem, error?`

---

## 5. 测试策略

### 契约
- `/v1/statement` 请求/响应 JSON Schema
- 必填 header 缺失 → 拒绝

### 单元
- LangGraph Trino client 封装(分页拉结果、错误映射)

### 集成
- Testcontainers 起 Trino + pgvector
- 跑:`SELECT * FROM client LIMIT 10` ✅
- 跑:`DROP TABLE client` → 拒绝 ❌
- 跑:超时长查询 → 60s 自动取消

### E2E
- LangGraph 完整链路命中 Trino,Langfuse 看到 query_id

### 安全
- 不带 `X-Trino-User` → 拒绝
- 用 RM A 身份查 RM B 数据(Phase 2 启 Ranger 后) → 行被过滤

### 可观测
- `text2sql_trino_query_total{state}`、`text2sql_trino_query_latency_ms_bucket`
- Trino 自身指标走 JMX exporter → Prometheus

---

## 6. 待确认

- Phase 2 是否引入 Apache Ranger(社区镜像维护一般)
- 是否需要把 PG 业务样例与生产 PG 副本通过 Trino federation 同时暴露
- Resource group 是否按 role(RM 较松,Compliance 较紧)分组
- 审计日志 7 年归档管道(ClickHouse vs S3+对象锁)
