# L4 — 能力层(Capability)

> 五个独立能力服务 + 一个嵌入库:
> **LiteLLM**(模型网关)· **Ollama**(本地模型)· **TEI**(嵌入/重排)· **Presidio**(PII)· `sqlglot`(嵌入 L5,不单独服务)

---

## 1. 模块映射

| 模块 | 镜像 | 端口 | 角色 |
|---|---|---|---|
| LiteLLM Proxy | `ghcr.io/berriai/litellm:main-latest` | 4000 | OpenAI 兼容 Gateway |
| Ollama | `ollama/ollama:latest` | 11434 | 本地兜底 LLM |
| TEI Embed | `ghcr.io/huggingface/text-embeddings-inference:cpu-latest` | 8082 | bge-m3 嵌入 |
| TEI Rerank | (同镜像,另一容器) | 8083 | bge-reranker-v2-m3(可选) |
| Presidio Analyzer | `mcr.microsoft.com/presidio-analyzer` | 5001 | PII 检测 |
| Presidio Anonymizer | `mcr.microsoft.com/presidio-anonymizer` | 5002 | PII 脱敏 |
| sqlglot | (Python 库) | — | SQL AST 解析/校验/方言转换 |

---

## 2. LiteLLM(模型网关)

### 2.1 路由(`config/litellm/config.yaml` 草案)
```yaml
model_list:
  - model_name: router/sql-gen
    litellm_params:
      model: azure/gpt-4o          # 由 .env 注入 key
      temperature: 0.0
      timeout: 30
  - model_name: router/general-small
    litellm_params:
      model: azure/gpt-4o-mini
  - model_name: ollama/qwen2.5-7b
    litellm_params:
      model: ollama_chat/qwen2.5:7b-instruct-q4_K_M
      api_base: http://ollama:11434

litellm_settings:
  callbacks: ["langfuse"]          # LANGFUSE_PUBLIC_KEY/SECRET 由 .env
  drop_params: true
  cache: false                     # 防口径漂移误命中

router_settings:
  fallbacks:
    - { "router/sql-gen": ["ollama/qwen2.5-7b"] }
  num_retries: 1
  request_timeout: 30

general_settings:
  master_key: "sk-${LITELLM_MASTER_KEY}"
```

### 2.2 输入输出约束
- 调用方必须传 `metadata.{trace_id,user_id,session_id,generation_name}`
- 仅 LangGraph 调 LiteLLM;Chainlit / 其他不得直连
- 出公网仅此一处;`.env` 集中管 key

---

## 3. Ollama(本地兜底)

### 3.1 默认模型(GPU 8-12GB 适配)
- `qwen2.5:7b-instruct-q4_K_M` ~5 GB(SQL 生成兜底)
- 备选:`qwen2.5-coder:7b-instruct-q4_K_M`(代码/SQL 更强)
- **不**默认装 `qwen2.5:14b`(显存紧张)

### 3.2 输入输出约束
- 仅 LiteLLM 路由调用;不允许 LangGraph 直连
- 启动后必须 `ollama pull <model>`,镜像不自带模型

---

## 4. TEI(嵌入 / 重排)

### 4.1 模型选型(8-12GB 显存)
| 实例 | 模型 | 显存 | 维度 |
|---|---|---|---|
| 嵌入 | `BAAI/bge-m3` | ~2 GB(GPU) | 1024 |
| 重排 | `BAAI/bge-reranker-v2-m3` | ~2 GB(GPU) | — |

> 已下载 `cpu-latest`,GPU 加速建议另拉 GPU 镜像(后续单独决策)。

### 4.2 接口(C5)
- `POST /embed` `{inputs:[...]}` → `{embeddings:[[...]]}`
- `POST /rerank` `{query, texts:[...]}` → `{results:[{index,score}]}`

### 4.3 输入输出约束
- 一次最多 32 条输入(超出 LangGraph 切片)
- 嵌入维度由模型决定,**变更模型 = 重建 pgvector 索引**(写在 Runbook)

---

## 5. Presidio(PII)

### 5.1 接口(C6)
- `POST /analyze` → entities[]
- `POST /anonymize` → 脱敏后文本

### 5.2 实体集(中英)
- 默认开:`PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE, IP_ADDRESS, US_SSN`
- CIB 加: 客户号(`CIF_ID`)、账户号(`ACCOUNT_NO`)— 走 **自定义识别器**(`config/presidio/recognizers/*.yaml`)

### 5.3 输入输出约束
- 入口阈值:`score ≥ 0.85` 必脱敏后再送 LLM
- 出口策略:列级配置(`config/presidio/output_policy.yaml`),如 `transaction.counterparty_name → mask` 但 `client.cif_id → keep(role∈{Compliance})`

---

## 6. sqlglot(嵌入 L5 的 SQL 校验器)

### 6.1 校验规则(`app/langgraph-app/validators/sqlglot_rules.py` 设计意图)

| 规则 | 失败码 |
|---|---|
| 仅 `SELECT`(允许 `WITH ... SELECT`) | `non_select` |
| 禁 DDL/DML/系统表/危险函数 | `forbidden_op` / `forbidden_function` |
| 表/列必须在白名单 | `unauth_table` / `unauth_column` |
| 跨敏感域 JOIN 拒绝 | `cross_domain_join` |
| 无 `LIMIT` → 自动注入 `LIMIT N` | `auto_limit_injected`(warning) |
| 大表无分区/时间过滤 | `missing_partition_filter` |
| 子查询深度 > 5 | `nesting_too_deep` |
| 笛卡尔积(无 join 条件) | `cartesian_join` |

### 6.2 输入输出
```python
def validate(sql: str, *, dialect: str, allowed_tables: set[str], allowed_columns: set[str]) -> SqlValidationResult
```
返回 `safe / sql_normalized / violations[] / tables_used / columns_used / auto_modifications[]`。

---

## 7. 跨模块约束(L4 内部)

- LiteLLM **不**调用 Presidio;脱敏由 LangGraph 在调 LiteLLM 之前完成
- TEI 嵌入维度变更需要联动 pgvector schema 升级(联动 [L3](./L3-knowledge.md))
- sqlglot 方言必须与 Trino catalog 方言一致(默认 `trino`)

---

## 8. 测试策略

### 契约
- LiteLLM `/v1/chat/completions` 请求/响应 Schema(JSON Schema)
- TEI `/embed` `/rerank` Schema
- Presidio `/analyze` `/anonymize` Schema

### 单元
- sqlglot 规则:**50+ SQL 样本**(每条规则 ≥ 3 用例)
- Presidio 自定义识别器(CIF_ID/ACCOUNT_NO):各 ≥ 10 正/负例

### 集成
- Testcontainers 拉 LiteLLM(`mock_response`)、Presidio、TEI(CPU)
- 端到端 嵌入→检索 流程

### Eval
- 同套 SQL Golden Set 在 `gpt-4o` vs `qwen2.5:7b` 对比基线

### 安全
- Presidio 漏检 → 视为 P1 用例,补识别器
- LiteLLM key 误用(其他服务伪装 LangGraph)→ 401

---

## 9. 待确认

- 行内可用的云模型清单 + 每月预算
- Ollama 模型是否预热进镜像还是 entrypoint pull
- Presidio CIF_ID/ACCOUNT_NO 的正则与样例由谁提供
- TEI 是否走 GPU 镜像(影响 `docker-compose` 的 `runtime: nvidia`)
