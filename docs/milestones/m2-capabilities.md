# Phase 2 — RAG + Security 实施记录

> 对应 ADR-0004。延续 Phase 1 walking skeleton,在管道中加入安全栏 (PII / 注入 / OPA) 与
> 检索栏 (pgvector + TEI),并解锁 self-repair 单次重试。

## 已实现(代码层)

| 模块 | 路径 | 状态 |
|---|---|---|
| 契约扩展 (PII / OPA / SchemaCard) | `packages/contracts/text2sql_contracts/state.py` | ✅ |
| 多表 schema 卡片 (client / account / exposure) | `services/langgraph-app/app/schema_catalog.py` | ✅ |
| 多表种子数据 (30 accounts + 25 exposures) | `config/postgres-cib/init/02_seed_account_exposure.sql` | ✅ |
| pgvector 卡片表 + ivfflat 索引 | 同上 (`schema_card`) | ✅ |
| **节点 `pii_guard`** (Presidio + 注入规则) | `app/nodes/pii_guard.py` | ✅ |
| **节点 `schema_link`** (pgvector top-K) | `app/nodes/schema_link.py` | ✅ |
| **节点 `opa_check`** (Rego + 离线 fallback) | `app/nodes/opa_check.py` | ✅ |
| Rego 策略 `text2sql.decision` | `config/opa/policies/text2sql.rego` | ✅ |
| Self-repair 单次重试 | `app/graph.py` (`SELF_REPAIR_MAX=1`) | ✅ |
| Compose: presidio-analyzer/anonymizer + tei-embed + opa | `compose/40-capability.yml` | ✅ |
| 单元测试: 30+ 新增用例 | `services/langgraph-app/tests/unit/test_*.py` | ✅ 92 pass |
| 红队用例 (20 注入 / DDL,4 合法) | `tests/unit/test_security_redteam.py` | ✅ 100% 拦截 |
| Phase 2 E2E 测试 | `tests/e2e/test_phase2_security_and_rag.py` | ✅ 待 stack up 后跑 |
| ADR 0004 | `docs/adr/0004-phase2-rag-and-security.md` | ✅ |

## 管道(Phase 2)

```
pii_guard ──► (refuse on PII / injection)
   │
   ▼
schema_link (pgvector + TEI top-K)
   │
   ▼
sql_generate (RAG-augmented prompt)
   │
   ▼
sql_validate ◄──► sql_generate (self-repair, max 1)
   │
   ▼
opa_check (Rego or offline fallback)
   │
   ▼
execute (Trino, X-Trino-User)
```

## 一次性首跑步骤

```powershell
cd text2sql-platform
# 1) 沿用 Phase 1 .env (DEEPSEEK_API_KEY 必填)
# 2) 起栈 (现已包含 Phase 2 capability 层)
make up-min          # vendor + build + up; 拉取 Presidio/TEI/OPA 镜像 ~3GB
make ps
make health

# 3) 单测 (本地 venv,无需 docker)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e packages/contracts -e "services/langgraph-app[dev]" asyncpg
cd services/langgraph-app && python -m pytest -m "not e2e" -v

# 4) Phase 2 E2E
cd ../..
make test-e2e-phase2
```

## 验收清单 (ADR-0004)

- [x] 92 个单测全绿(含 20 条注入红队 + 4 条合法用例,100% 拦截)
- [ ] `make up-min` 启动 7 + 4 个容器并健康
- [ ] Phase 2 E2E:多表 join 成功 / 注入拒绝 / PII 拒绝 / OPA 拒绝
- [ ] Schema-link Recall@5 ≥ 90%(后续补 fixture,本次以 hand-eval 验证 3 条问题)

## 已知 gap(Phase 3 处理)

| Gap | 计划 |
|---|---|
| 没有 `langgraph.StateGraph` (仍是 hand-rolled async) | Phase 3 — 需要 approval 分支时切 |
| Cube `/meta` 仍未接入(卡片手写) | Phase 3 |
| DataHub 未 ingest | Phase 3 |
| Reranker (TEI 二实例) 未启 | Phase 3 |
| Argilla / Promptfoo CI | Phase 3 |
| 出参脱敏(只对 PII 入参拦截) | Phase 3 |

## 防跑偏 6 卡口落地

| 卡口 | 落点 | 状态 |
|---|---|---|
| 架构=宪法 | ADR-0004 + 此文档每条偏离都点名 | ✅ |
| 契约=单一真相源 | `packages/contracts` 新增 PII/OPA/SchemaLink + 现有 roundtrip 测试 | ✅ |
| CI 七层卡口 | 新红队层 + 既有契约/单元;集成/eval 待 Phase 3 | 🟡 |
| ADR 机制 | 0001-0004 | ✅ |
| 周 demo | up-min 后录注入拒绝 + 多表 join 双场景 | ⏳ |
| Slice DoD 模板 | 仍用 `docs/slice-template.md` | ✅ |
