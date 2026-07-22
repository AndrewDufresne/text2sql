# ADR 0003 — Walking Skeleton Scope

- **Status**: Accepted
- **Date**: 2026-05-05

## Context

Phase 1 完成标准是"1 个问题→SQL→结果→trace 完整"。八层架构里仍有可拆解空间——若一上来就启 DataHub + Cube + 全节点 + 全测试,W1 末必跑不完。

## Decision

Walking Skeleton (Slice 1.1 + 1.2) **最小可演示集**:

### 范围内
- **数据**:单表 `cib.client`(20 行合成数据,无 PII)
- **Compose**:`network + state(pg, pgv) + platform(litellm, langfuse) + data(trino) + app(langgraph, chainlit)`. LLM = DeepSeek API(详见 ADR-0002)
- **LangGraph 节点**:`sql_generate → sql_validate → execute`(3 个,无 self-repair、无 OPA、无 Presidio)
- **Schema 来源**:**硬编码**在 prompt 中(单表 schema 文本)。Cube `/meta` 在 Slice 1.3 接入
- **测试**:契约 + 单元(`sql_validate` 50 例) + 1 条 E2E(walking skeleton)

### 范围外(Phase 1 后续 slice 或 Phase 2)
- Cube 语义层、DataHub、pgvector、TEI、Presidio、OPA、Argilla
- self-repair loop、approval、PII 出口脱敏
- 多表 join、复杂聚合

## Consequences

- ✅ W1 末可演示端到端
- ✅ 每加一个组件 = 一次纵切片,可独立 demo
- ⚠️ Slice 1.3 接 Cube 时需重写 `sql_generate` prompt — 已在 backlog 标注
