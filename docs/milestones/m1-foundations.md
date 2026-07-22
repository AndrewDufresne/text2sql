# Phase 1 — Walking Skeleton 实施记录

> 对应 ADR-0003。本文档记录 Phase 1 落地的**结构、运行步骤、已知 gap、下一步**。

## 已实现(代码层)

| 模块 | 路径 | 状态 |
|---|---|---|
| 契约 (Pydantic) | `packages/contracts/text2sql_contracts/` | ✅ |
| 契约 round-trip 测试 | `packages/contracts/tests/test_contracts.py` | ✅ |
| LangGraph App 骨架 | `services/langgraph-app/app/` | ✅ 3 节点 |
| `sql_validate` 单元测试(50+ 例) | `services/langgraph-app/tests/unit/test_sql_validate.py` | ✅ |
| 图运行器单元测试 | `services/langgraph-app/tests/unit/test_graph_runner.py` | ✅ |
| Chainlit UI | `services/chainlit-ui/app/chainlit_app.py` | ✅ |
| Compose 文件 | `compose/00,10,20,30,50` | ✅ |
| Trino 配置 + cib catalog | `config/trino/etc/` | ✅ |
| Postgres 种子(20 行 client) | `config/postgres-cib/init/01_seed_client.sql` | ✅ |
| LiteLLM 配置(DeepSeek API) | `config/litellm/config.yaml` | ✅ |
| Walking-skeleton E2E 测试 | `tests/e2e/test_walking_skeleton.py` | ✅ |
| Makefile / VS Code tasks | `Makefile` / `.vscode/tasks.json` | ✅ |
| ADR 0001-0003 | `docs/adr/` | ✅ |
| CI 七层骨架 | `.github/workflows/ci.yml` | ✅ 占位 |

## 一次性首跑步骤

```powershell
cd text2sql-platform
Copy-Item .env.example .env
notepad .env     # 填入 DEEPSEEK_API_KEY=sk-...

# 1) 容器构建会复制 contracts 包,需要在 build 前 vendor 一次
#    (临时方案,Phase 2 改为 monorepo 工具)
mkdir services\langgraph-app\vendor 2>$null
mkdir services\chainlit-ui\vendor   2>$null
xcopy /E /I /Y packages\contracts services\langgraph-app\vendor\text2sql-contracts
xcopy /E /I /Y packages\contracts services\chainlit-ui\vendor\text2sql-contracts

# 2) 起栈
make up-min     # or: 用 VS Code task "compose: up-min"

# 3) 等服务健康
make ps
make health

# 4) 单测
make test-unit

# 5) E2E
make test-e2e

# 6) 打开 UI
start http://localhost:8000          # Chainlit
start http://localhost:3000          # Langfuse(用 admin@t2sql.local / admin_dev_only 登录)
```

## 验收(Phase 1 完成判定)

- [ ] `make test-unit` 全绿(契约 + 50+ SQL 校验 + 3 graph runner 用例)
- [ ] `make up-min && make health` 全绿
- [ ] Chainlit 中提问 *"How many active clients are there?"*,得到含 SQL + 表格的回复
- [ ] Langfuse UI 能看到对应 trace,包含 `sql_generate / sql_validate / execute` 三个 span
- [ ] `make test-e2e` 全绿

## Phase 1 已知 gap(下一阶段处理,不在本期内修复)

| Gap | 计划 |
|---|---|
| Cube `/meta` 未接入(schema 仍硬编码) | Slice 1.3 — 下一 PR |
| DataHub 未 ingest | Slice 1.4 — 独立 compose,不阻塞 |
| OPA / Presidio / pgvector 未启 | Phase 2 |
| 多表 join、self-repair、approval | Phase 2 |
| Promptfoo eval 阻断阈值 | Phase 3 |
| Prom/Grafana 大盘 | Phase 4 |
| 真 Langfuse 自动注入(LiteLLM callback)端到端验证 | 等 Slice 1.1 起栈后人工确认 |

## 防跑偏 6 卡口在本期落地情况

| 卡口 | 落点 | 状态 |
|---|---|---|
| 架构=宪法 | 本文档每条偏离都点名了 ADR | ✅ |
| 契约=单一真相源 | `packages/contracts` + roundtrip 测试 | ✅ |
| CI 七层卡口 | `.github/workflows/ci.yml` 7 个 job(部分占位) | ✅ |
| ADR 机制 | `docs/adr/0001-0003` + README | ✅ |
| 周 demo | 等首跑后录 demo | ⏳ |
| Slice DoD 模板 | `docs/slice-template.md` | ✅ |
