# L3 — 知识层(Knowledge)

> 三个组件:**Cube**(语义层)· **DataHub**(目录/术语/血缘)· **pgvector**(向量库,与业务样例同库)
> 试点数据域:**CIB 客户 360**(`client / account / exposure / transaction`)

---

## 1. 模块映射

| 模块 | 镜像 | 端口 | 角色 |
|---|---|---|---|
| Cube | `cubejs/cube:latest` | 4040 | 度量/维度受控定义 |
| pgvector(同业务样例库) | `pgvector/pgvector:pg16` | 5433 | 业务样例数据 + 向量索引(`schema_chunks`) |
| DataHub | `acryldata/datahub-*` + Kafka/ES/MySQL | Frontend `9002`, GMS `8080→8090` | 数据目录、术语词典、血缘、PII 标签 |

> **决策**:Phase 1 用 `datahub docker quickstart`(单独 compose,可独立启停);若 8GB+ 占用过重再切精简版。

---

## 2. 试点 Schema(CIB 客户 360)

### 2.1 物理表(pgvector 库的 `cib` schema)
```sql
client(cif_id PK, name, country, segment, rm_owner, kyc_level, created_at)
account(account_no PK, cif_id FK, ccy, status, opened_at, balance)
exposure(exposure_id PK, cif_id FK, product, ccy, exposure_amt, limit_amt, as_of_date)
transaction(txn_id PK, account_no FK, txn_type, ccy, amount, counterparty_name, txn_ts)
```
- `client.name`, `transaction.counterparty_name` → PII(出口必脱敏)
- `client.cif_id`, `account.account_no` → PII(角色相关)
- 数据来源:**Faker 合成**,固定种子,5k 客户 / 10k 账户 / 50k 敞口 / 200k 流水

### 2.2 Cube 定义(`config/cube/schema/*.yml` 草案)
- `cubes/Client.yml`:维度 `cif_id, segment, country`;度量 `count`
- `cubes/Exposure.yml`:维度 `product, ccy, as_of_date`;度量 `total_exposure (sum), client_count(distinct cif_id)`;`joins: Client`
- `cubes/Transaction.yml`:同理
- `views/CustomerExposureMonthly.yml`:对外暴露的"客户月度敞口视图"

### 2.3 DataHub 资产
- Dataset:Trino catalog 同步(`pgvector_cib.cib.client` 等)
- Glossary Terms:`敞口=Exposure.total_exposure`、`活跃客户=...`、`AUM=...`(术语→Cube measure 映射)
- Tags:`PII:NAME`、`PII:ACCOUNT_NO`、`Sensitivity:C2/C3`
- Lineage:Cube view → 物理表 → 上游(Phase 2 后做)

---

## 3. 输入输出约束

### 3.1 LangGraph → Cube(C7)
- 优先调 `/v1/meta` + 拼 `/v1/load` 走受信任度量
- 无匹配度量时降级到原始表(Trino 直查),并在 trace 标 `degraded=true`
- Cube 鉴权:JWT,LangGraph 注入 `{user_id, role, business_unit}`,Cube `securityContext` 做 RLS

### 3.2 LangGraph → DataHub(C8)
- 仅查询;不写入(写入由数据治理流程)
- 用作 **Schema Linking 的术语来源**(术语→列/度量映射)
- 不可用时降级,不阻断主流程

### 3.3 LangGraph → pgvector(C9)
- 表 `schema_chunks(id, source, business_unit, text, embedding vector(1024), metadata jsonb, updated_at)`
- HNSW 索引(`vector_cosine_ops`)
- 写入来源:Cube meta、DataHub Glossary、表/列描述、历史 Q&A
- 重建索引:模型/维度变更时通过 Airflow / 手动脚本(Runbook)

### 3.4 数据回填管道(三个来源 → pgvector)
- `loaders/cube_loader.py`:Cube `/meta` → chunks
- `loaders/datahub_loader.py`:DataHub Glossary + Dataset desc → chunks
- `loaders/qna_loader.py`:Argilla Golden Set → chunks
- 调度:Phase 1 手动 `make refresh-knowledge`;Phase 4 接 Airflow

---

## 4. 跨模块约束(L3 内部)

- Cube measure 名 ↔ DataHub Glossary term:**字段名一一对应**(治理强约束)
- pgvector `metadata` 至少含 `source`、`source_id`、`updated_at`,以便溯源
- 任一来源更新 → 触发对应 chunk 重新嵌入 + upsert(不全量重建)

---

## 5. 安全约束

- pgvector 业务样例库:Trino 用专属只读账户访问(不能 DDL/DML)
- Cube `securityContext`:基于 role 的 RLS(如 RM 只能看自己的客户)
- DataHub:外部访问鉴权 (Phase 2 接 SSO)

---

## 6. 测试策略

### 契约
- Cube `/meta` 响应字段、`/load` 请求 schema
- DataHub OpenAPI 关键端点

### 单元
- 每个 loader(cube/datahub/qna)的 chunk 生成纯函数
- pgvector retriever 函数(SQL 拼装、过滤器)

### 集成
- Testcontainers:pgvector + Cube + Trino,起最小数据集 → loader → 检索 ≥ 1 命中
- DataHub 单独跑 quickstart smoke(夜间)

### E2E
- "查 5 个最大敞口客户" → schema_link 命中 `Exposure.total_exposure` → SQL 走 Cube view

### 安全
- Cube RLS:RM A 查询 RM B 客户 → 行被过滤为空
- pgvector 只读账户尝试 INSERT → 拒绝

### 可观测
- 每次检索:`text2sql_retrieve_recall_at_k`、`text2sql_retrieve_latency_ms`

---

## 7. 待确认

- 试点 Faker 合成数据生成脚本 Owner
- DataHub 启动后是否需要"种子术语"批量导入(由谁产出 YAML)
- Cube RLS 策略具体到哪个粒度(RM/BU/Country)
- pgvector 与 Postgres 平台元数据库是否共用一套 PG 实例(建议**分开**,避免相互影响)
