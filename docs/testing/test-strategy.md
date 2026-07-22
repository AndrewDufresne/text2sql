# 测试驱动(TDD)总策略

> 版本:v0.1
> 原则:**任何 PR 必须先有失败测试,再补实现。无测试 = 不合并。**

---

## 1. 测试金字塔(七层)

```
                      ┌───────────────────┐
                      │ 7. 可观测性测试    │  少量
                      ├───────────────────┤
                      │ 6. 安全/红队测试   │  少量
                      ├───────────────────┤
                      │ 5. Eval(LLM 质量) │  中等(Golden Set)
                      ├───────────────────┤
                      │ 4. E2E             │  少量(Compose 起栈)
                      ├───────────────────┤
                      │ 3. 集成            │  中等(Testcontainers)
                      ├───────────────────┤
                      │ 2. 单元            │  大量
                      ├───────────────────┤
                      │ 1. 契约(Schema)   │  大量(快、CI gate)
                      └───────────────────┘
```

---

## 2. 各层测试规约

### Layer 1 — 契约测试(Contract Tests)
- **范围**:[contracts/io-contracts.md](../contracts/io-contracts.md) 中所有 C1–C15。
- **工具**:`pydantic` + `jsonschema` + 自写 `pytest` fixtures。
- **要点**:
  - 每个请求/响应 schema 都有 ≥ 3 个用例:**最小有效 / 完整有效 / 各字段越界**。
  - 对 HTTP 接口同时维护 OpenAPI(`schemas/openapi.yaml`)。
- **CI**:每 PR 跑;< 30s。

### Layer 2 — 单元测试(Unit)
- **范围**:LangGraph 每个节点函数、sqlglot 校验器、PII 调用封装、retriever、OPA 客户端。
- **工具**:`pytest` + `pytest-asyncio` + `respx`(HTTP mock)+ `pytest-mock`。
- **覆盖率门禁**:行覆盖 ≥ 85%,分支覆盖 ≥ 75%(`pytest --cov`)。
- **mock 原则**:**不 mock 自己写的代码**;只 mock 网络边界。

### Layer 3 — 集成测试(Integration)
- **范围**:LangGraph App 与真实 PG/Trino/LiteLLM/OPA/TEI/Presidio 的交互。
- **工具**:`testcontainers-python`,起轻量化容器(同 Phase 1 镜像)。
- **数据**:每个 case 用 `pytest fixture` 灌入隔离 schema。
- **LLM 调用**:LiteLLM 配 `mock_response`(LiteLLM 原生支持),不打真模型。
- **CI**:每 PR 跑;< 5 min。

### Layer 4 — E2E 测试
- **范围**:`docker compose up` 起 Phase 1 全栈,跑端到端用例。
- **工具**:`pytest` + `playwright`(Chainlit UI)+ `httpx`(API)。
- **用例**(必须):
  1. Happy path:1 个标准 CIB 客户查询 → SQL → 结果 → trace 出现在 Langfuse。
  2. 模糊问题 → `need_clarify` 分支。
  3. 越权问题 → `refused`,OPA 拒绝原因落 trace。
  4. 注入文本 → 拦截 + Argilla 记录。
- **CI**:每日夜间;失败阻断 release。

### Layer 5 — Eval(LLM 质量)
- **范围**:Promptfoo + Golden Set。
- **数据集**:
  - `golden_v1`:300 题 CIB 客户 360 域,每题含 `question, expected_sql_or_rows_hash, tags, difficulty`
  - `adversarial_v1`:50 题(注入 / PII 套取 / 越权 / 语义陷阱)
- **指标 + 阈值**(MVP 起):
  | 指标 | 阈值 |
  |---|---|
  | Result Match | ≥ 0.85 |
  | Execution Accuracy | ≥ 0.98 |
  | Schema Linking Recall@5 | ≥ 0.95 |
  | Refusal Precision | ≥ 0.99 |
  | Injection Block Rate | = 1.00 |
  | P95 Latency | ≤ 8000ms |
  | Avg Cost / Q | ≤ $0.02 |
- **CI**:Prompt / 模型 / Schema 链路任一变更 → 触发;低于阈值 → 阻断合入。
- **Diff 报告**:Promptfoo `share` 出 HTML,自动评论到 PR。

### Layer 6 — 安全 / 红队测试
- **范围**:OWASP LLM Top 10 中适用项 + SQL 注入 + 越权。
- **工具**:`pytest` 用例库 + `garak`(可选)+ `Promptfoo` 安全 plugins。
- **必拦用例**(摘):
  - `'; DROP TABLE x; --` 类注入
  - "ignore previous instructions" 类越权
  - 套取他人客户(role=RM 但查别人客户的 cif)
  - 套取 PII(身份证 / 手机号回显)
- **CI**:每 PR 跑(快子集);夜间跑全集。

### Layer 7 — 可观测性测试
- **范围**:trace 完整性、metric 暴露、log 字段、健康检查。
- **断言示例**:
  - 一次 E2E 请求后,Langfuse 应有 1 trace + ≥ 7 spans + ≥ 1 generation
  - `text2sql_node_latency_ms{node="sql_generate"}` 在 Prometheus `/metrics` 中存在且非空
  - Loki 中存在 `trace_id=<x>` 的至少 N 条结构化日志
  - Tempo 中能按 `trace_id` 检索到分布式 trace,跨 ≥ 3 个服务
- **CI**:E2E 套件之一,夜间跑。

---

## 3. 目录与命名约定

```
app/langgraph-app/
├── tests/
│   ├── contract/          # Layer 1
│   ├── unit/              # Layer 2  (镜像源代码目录)
│   ├── integration/       # Layer 3
│   ├── e2e/               # Layer 4
│   ├── security/          # Layer 6
│   ├── observability/     # Layer 7
│   └── conftest.py
evals/
├── promptfoo/
│   └── promptfooconfig.yaml
└── golden_set/
    ├── cib_customer360_v1.yaml
    └── adversarial_v1.yaml
```

测试文件命名:`test_<module>_<behavior>.py`,函数 `test_<gives>_<when>_<then>`。

---

## 4. TDD 工作流(强制)

每个新功能/Bug 修复:
1. **写失败测试**(契约或单元层)→ 提交 PR `[red]` 标签 → CI 应红。
2. **最小实现** → CI 转绿 → PR 标 `[green]`。
3. **重构 + 补充其他层测试**(集成/E2E/Eval)→ `[refactor]`。
4. **更新文档与契约**(若涉及边界)。

合并门禁:
- 契约 + 单元 + 集成 全绿
- 覆盖率不下降
- 若改动触及 Prompt/模型/Schema → Eval 必须达阈值

---

## 5. 测试数据治理

| 类别 | 来源 | 存放 | 注意 |
|---|---|---|---|
| 业务样例(CIB 客户 360) | 合成数据(`Faker` + 种子) | `data/seeds/cib/*.sql` | 不含真实客户 |
| Golden Set 问句 | 业务专家 + LLM 草拟 + 人审 | `evals/golden_set/*.yaml` | 版本化 + Owner |
| 对抗用例 | 红队 + OWASP LLM Top10 | `evals/golden_set/adversarial_*.yaml` | 仅内部 |
| Trace fixture | 录制(LiteLLM cassettes / VCR) | `tests/cassettes/` | PR 评审务必看 diff |

---

## 6. CI 流水线(GitHub Actions 草案)

```yaml
on: [pull_request]
jobs:
  contract-unit:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/contract tests/unit --cov=app --cov-fail-under=85
  integration:
    runs-on: ubuntu-latest
    services: { docker: {} }
    steps:
      - run: pytest tests/integration -m "not slow"
  eval:
    if: contains(github.event.pull_request.changed_files, 'prompts/') ||
        contains(github.event.pull_request.changed_files, 'app/langgraph-app/nodes/')
    steps:
      - run: npx promptfoo eval -c evals/promptfoo/promptfooconfig.yaml --no-cache
      - run: npx promptfoo share | tee promptfoo-url.txt
  security:
    steps:
      - run: pytest tests/security -m "fast"
nightly:
  schedule: [{ cron: "0 18 * * *" }]
  jobs:
    e2e:    { steps: [ ... compose up + pytest tests/e2e ... ] }
    full-eval: { steps: [ ... 全集 + adversarial 全集 ... ] }
```

---

## 7. 验收门禁(Definition of Done)

PR 合并条件:
- [ ] 至少 1 个失败→通过的测试
- [ ] 契约/单元/集成 全绿
- [ ] 覆盖率不下降
- [ ] 若涉及 Prompt/Model/Schema → Eval 达阈值
- [ ] 涉及边界 → `contracts/io-contracts.md` 同步更新
- [ ] 涉及新模块 → `layers/L*.md` 子架构更新
- [ ] 安全敏感改动(OPA/Presidio/sqlglot) → 红队用例 + 人审

---

## 8. 待确认

| # | 问题 | 影响 |
|---|---|---|
| T1 | Golden Set 标注由谁负责?(业务 SME / 数据团队) | 数据质量与节奏 |
| T2 | CI 平台:GitHub Actions / GitLab CI / Jenkins? | 流水线写法 |
| T3 | 是否引入 `mutmut` 等变异测试? | 测试有效性度量 |
| T4 | Eval 阈值是否分业务域分别设? | 报告与门禁粒度 |
