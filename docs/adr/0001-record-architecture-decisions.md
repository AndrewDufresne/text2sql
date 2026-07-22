# ADR 0001 — Record Architecture Decisions

- **Status**: Accepted
- **Date**: 2026-05-05
- **Deciders**: Architecture owner

## Context

复杂八层架构 + 4 Phase,跨多个团队/技术栈。若没有显式决策记录,半年后无人能回答"当初为什么选 X"。

## Decision

采用 MADR-lite 格式,在 `docs/adr/` 维护 ADR。任何偏离 `Architecture.md` 的决定必须先 PR 一份 ADR 才能改实现。

## Consequences

- ✅ 决策可追溯,新成员 onboarding 快
- ✅ 防止"无声漂移"(组件被悄悄替换)
- ⚠️ 增加 PR 流程开销 → 仅对**架构级**决定写 ADR,不为日常代码改动写
