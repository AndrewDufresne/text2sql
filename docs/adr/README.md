# Architecture Decision Records (ADR)

> Format: [MADR](https://adr.github.io/madr/) lite. One file per decision, immutable once accepted.

## Process

1. 任何**偏离** [`Architecture.md`](../Architecture.md) 的决定(换组件、调端口、跳层调用、降级实现)→ 写 ADR。
2. 文件名:`NNNN-short-title.md`(NNNN 顺序递增)。
3. PR 标题包含 `ADR-NNNN`,review ≥ 1 人 + 架构 owner。
4. 状态流转:`Proposed → Accepted | Rejected | Superseded by NNNN`。

## Index

| # | Title | Status |
|---|---|---|
| 0001 | [Record architecture decisions](./0001-record-architecture-decisions.md) | Accepted |
| 0002 | [Phase 1 LLM provider = DeepSeek API](./0002-phase1-llm-provider-deepseek.md) | Accepted |
| 0003 | [Walking skeleton scope: single table `client`, 3 nodes](./0003-walking-skeleton-scope.md) | Accepted |
