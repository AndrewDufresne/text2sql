# ADR 0002 — Phase 1 LLM Provider = DeepSeek API

- **Status**: Accepted
- **Date**: 2026-05-05
- **Supersedes**: prior draft "Phase 1 LLM = Ollama"

## Context

`Architecture.md` 规划 LiteLLM 路由到云模型(主)+ Ollama(兜底)。Phase 1 walking
skeleton 阶段需要一个**确定可用、零本地资源占用**的 LLM provider:

- 行内云模型清单 / Azure OpenAI 接入(Q2)未敲定,不能等
- 本地 Ollama 7B 在无 GPU 机器上 SQL 生成质量极低,且占 5+ GB 显存
- 需要一个 OpenAI 兼容、便宜、SQL 能力达标的 API → **DeepSeek**

## Decision

Phase 1 **LiteLLM 仅配 DeepSeek 一条路由**:

- `router/sql-gen` → `deepseek/deepseek-chat`(DeepSeek-V3,temp 0.0)
- `router/general-small` → `deepseek/deepseek-chat`(temp 0.2,用于 NL 解释)
- `router/sql-gen-reasoner` → `deepseek/deepseek-reasoner`(R1,预留,默认关闭)

不再启动 `ollama` 容器。LiteLLM 配置文件预留 Azure / OpenAI 注释段,Phase 2
启用其他 provider 前再写 ADR-00XX。

## Consequences

- ✅ 零 GPU、零本地模型下载,任意开发机 `make up-min` 可跑通 walking skeleton
- ✅ DeepSeek-V3 SQL 能力强,Phase 1 Eval 仍可设 `Result Match ≥ 80%`(单表)
- ✅ Langfuse 自动通过 LiteLLM callback 记录 token + cost(USD,基于 DeepSeek 价目)
- ⚠️ **强依赖外部 API key + 公网出向**;`.env` 必须填 `DEEPSEEK_API_KEY`,
  否则 `make up-min` 起得来,但任何 query 会 502
- ⚠️ 数据出公网:Phase 1 数据是合成的,无 PII;Phase 2 接入真数据前必须切回
  行内云模型,且必须先实现 Presidio 入口脱敏(架构 §S3 / §S6)
- ⚠️ 速率/配额受 DeepSeek 套餐约束 → 不要用 walking skeleton 跑大规模 eval,
  Promptfoo CI(Phase 3)按需切回行内模型
