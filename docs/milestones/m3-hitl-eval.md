# Phase 3 — HITL + Eval 实施记录

> 对应 ADR-0005。延续 Phase 2,在管道末端加入 NL 解释 + 出参 PII 脱敏,
> 暴露 `/api/v1/feedback` 写 Argilla(失败回退本地 JSONL),并以 Golden Set
> 作为质量门禁(`tests/eval/run_eval.py`,阈值 ≥ 90%)。

## 已实现(代码层)

| 模块 | 路径 | 状态 |
|---|---|---|
| 契约扩展 (Feedback / ExplanationResult / OutputMaskResult) | `packages/contracts/text2sql_contracts/{feedback,state,errors,query}.py` | ✅ |
| **节点 `explain`** (LiteLLM,非阻塞) | `services/langgraph-app/app/nodes/explain.py` | ✅ |
| **节点 `output_mask`** (Presidio + 离线回退) | `services/langgraph-app/app/nodes/output_mask.py` | ✅ |
| LiteLLM `generate_explanation` | `app/clients/litellm.py` | ✅ |
| Argilla 客户端 + JSONL 回退 | `app/clients/argilla_client.py` | ✅ |
| `POST /api/v1/feedback` 端点 | `app/main.py` | ✅ |
| Compose: Argilla quickstart | `compose/60-hitl.yml` | ✅ |
| Phase 3 env 注入 langgraph-app | `compose/50-app.yml` | ✅ |
| Golden Set (11 用例,3 类:正常 / 安全 / 授权) | `tests/eval/golden_set.yaml` | ✅ |
| Eval 执行器 (Python,无 Node 依赖) | `tests/eval/run_eval.py` | ✅ |
| Promptfoo 配置 (可选,本地探索用) | `tests/eval/promptfoo.yaml` | ✅ |
| CI 工作流: `eval` job (workflow_dispatch) + `security` 实跑 | `.github/workflows/ci.yml` | ✅ |
| 单测: output_mask + explain + feedback (15 用例) | `services/langgraph-app/tests/unit/test_{output_mask_and_explain,feedback}.py` | ✅ 107 pass 总计 |
| 契约测试: Feedback roundtrip + Phase 3 字段 | `packages/contracts/tests/test_contracts.py` | ✅ |
| Phase 3 E2E (4 用例,含 Golden Set 全跑) | `tests/e2e/test_phase3_hitl_and_eval.py` | ✅ 待 stack up 后跑 |
| Chainlit 渲染解释 + 脱敏计数 + feedback hint | `services/chainlit-ui/app/chainlit_app.py` | ✅ |
| Makefile / make.cmd: `up-hitl` `down-hitl` `eval` `test-e2e-phase3` | `Makefile` `make.cmd` | ✅ |
| ADR-0005 | `docs/adr/0005-phase3-hitl-and-eval.md` | ✅ |

## 管道(Phase 3 完整)

```
pii_guard ──► (refuse on PII / injection)
   │
   ▼
schema_link (pgvector + TEI top-K)
   │
   ▼
sql_generate ◄──► sql_validate (self-repair, max 1)
   │
   ▼
opa_check
   │
   ▼
execute (Trino, X-Trino-User)
   │
   ▼
explain  (LiteLLM,非阻塞,失败也返回 OK)
   │
   ▼
output_mask (Presidio 重跑结果集 + 解释,记录 entity_counts)
   │
   ▼
QueryResponse  (含 explanation / output_mask / feedback_url)
   │
   └──► (用户点 👍/👎/✏️) ──► POST /api/v1/feedback
                                  │
                                  ├─► Argilla (若 ARGILLA_ENABLED=true)
                                  └─► /tmp/text2sql-feedback.jsonl (回退)
```

## 一次性首跑步骤

```powershell
cd text2sql-platform

# 1) Phase 1/2 .env 不变;Phase 3 默认 ARGILLA_ENABLED=false (走本地回退)
#    若要启用 Argilla,在 .env 里加:
#       ARGILLA_ENABLED=true
#       ARGILLA_API_KEY=owner.apikey
#       ARGILLA_WORKSPACE=admin
#       ARGILLA_DATASET=text2sql-feedback

# 2) 起完整栈 (Phase 1+2+3)
make up-hitl       # vendor + build + up;首次拉 Argilla quickstart ~2GB,90s warm-up
make ps
make health

# 3) 单测 (本地 venv,无需 docker)
.\.venv\Scripts\Activate.ps1
pip install -e packages/contracts -e "services/langgraph-app[dev]" pyyaml
python -m pytest packages/contracts/tests services/langgraph-app/tests -m "not e2e" -v

# 4) Golden Set eval (需要 stack up)
make eval          # → tests/eval/report.json,退出码 0 通过 / 1 不通过

# 5) Phase 3 E2E (含 feedback + golden set)
make test-e2e-phase3
```

## 验收清单 (ADR-0005)

- [x] 单测 107 全绿(含 15 条 Phase 3 新增)
- [ ] `make up-hitl` 启动 12 容器(11 + Argilla)并健康
- [ ] `/api/v1/feedback` 接受 thumbs_up/down/correction
- [ ] Argilla 关闭时回退 `/tmp/text2sql-feedback.jsonl`,无丢数
- [ ] `make eval` Golden Set 通过率 ≥ 90%
- [ ] Phase 3 E2E:解释 / 脱敏 / 反馈 / golden-set 全绿

## Phase 3 防跑偏卡口

| 卡口 | 落点 | 状态 |
|---|---|---|
| 架构=宪法 | ADR-0005 显式列出"为何不做 DataHub / Reranker / Cube /meta" | ✅ |
| 契约=单一真相源 | `FeedbackRequest/Response` + `OutputMaskResult/ExplanationResult` 都在 `text2sql_contracts`,带 roundtrip 测试 | ✅ |
| CI 七层卡口 | 新增 `eval` job(workflow_dispatch);`security` 红队 job 改为实跑 | ✅ |
| ADR 机制 | 0001-0005 | ✅ |
| 周 demo | up-hitl → "活跃客户数" → 看 explanation + 点 👍 → Argilla UI 见到记录 | ⏳ |
| Slice DoD 模板 | `docs/slice-template.md` 不变 | ✅ |

## 已知 gap(Phase 4 处理)

| Gap | 计划 |
|---|---|
| `langgraph.StateGraph` (仍是 hand-rolled async) | Phase 4 需要 approval 分支时切 |
| Cube `/meta` 仍未接入 | Phase 4 |
| DataHub 未 ingest | Phase 4 |
| Reranker (TEI 二实例) 未启 | Phase 4 |
| SSO + 真实 user attribution | Phase 4 |
| Argilla quickstart → 拆分生产部署 | Phase 4 |
| Backstage 开发者门户 | Phase 4 |
| Prom/Grafana/Loki/Tempo 大盘 | Phase 4 |

---

## Phase 3.1 — Argilla schema 完整闭环(增量,无新 ADR)

> 目标:把 Phase 3 的 walking-skeleton Argilla 写入对齐到设计文档
> [`docs/layers/L6-hitl.md`](./layers/L6-hitl.md) §2.1 的完整 schema,并补
> 上"SME 标注 → Golden Set 回流"这条之前缺失的反向路径。
> 不引入新依赖,不动管道,完全向后兼容。

### Phase 3.1 已实现

| 模块 | 路径 | 备注 |
|---|---|---|
| `FeedbackRequest` 扩字段 | `packages/contracts/text2sql_contracts/feedback.py` | 新增 `failure_mode/result_preview/explanation/user_role/business_unit/model/prompt_version/metrics_used/cost_usd/latency_ms/question_embedding`,全部 optional,旧 caller 不动 |
| `FailureMode` StrEnum | 同上 | wrong_metric/wrong_join/wrong_filter/hallucination/perf/other |
| Argilla 客户端重写 | `services/langgraph-app/app/clients/argilla_client.py` | `record_id = trace_id`(确定性,可与 Langfuse join,可幂等覆盖);填充完整 `fields/metadata/vectors/responses`;`responses[0].status="submitted"` 让记录上 SME 看板就能看 |
| `corrected_sql` 二次防御 | 同上 | 入库前 `sqlglot.parse(...)`;失败则丢字段 + 打 tag `corrected_sql_parse_error`,SME 仍能看到原始 comment |
| Bootstrap CLI(幂等) | `tools/argilla/bootstrap.py` | 创建 workspace + dataset + 6 fields + 3 questions + 14 metadata-properties + 1 vector(dim 可配,默认 384 与 TEI 对齐) |
| Sync CLI(回流) | `tools/argilla/sync_golden.py` | 拉 `metadata.reviewed=true & golden_set_id` 空的记录 → `sql_validate.validate()` 二次校验 → 追加到 `tests/eval/golden_set.yaml`,并 PATCH `golden_set_id` 防重导;失败的 SQL 反向 unmark `reviewed` |
| Make 目标 | `Makefile` + `make.cmd` | `argilla-bootstrap` / `argilla-sync-golden`(Win + GNU 同步) |
| 单测 | `services/langgraph-app/tests/unit/test_feedback.py` + `tools/argilla/tests/` + `packages/contracts/tests/test_contracts.py` | 7 条新增:full schema 写入 / parse_error 拦截 / bootstrap 全量 schema 创建 / bootstrap 已发布幂等 / sync 追加 / sync 拒绝 / sync dry-run |

### Phase 3.1 验收清单

- [x] **120** 个单测 + 契约测试全绿(原 116 + 4 新增,bootstrap/sync 共 5 条)
- [x] `record_id == trace_id`(契约测试 + argilla 客户端测试都断言)
- [x] `corrected_sql` 不可解析时不入库,加 tag `corrected_sql_parse_error`
- [x] `responses[0].status="submitted"`,`thumb/corrected_sql/failure_mode` 三项预填
- [x] `vectors.question` 在 `question_embedding` 提供时随记录写入
- [x] Bootstrap CLI 幂等:dataset `status=ready` 时不再 POST schema
- [ ] (栈级别)`make up-hitl && make argilla-bootstrap`,UI 上看到完整 dataset(待 SIT 启栈验证)
- [ ] (栈级别)端到端:用户点 ✏️ → record 出现 → SME 标 reviewed=true → `make argilla-sync-golden` → `golden_set.yaml` 多一条

### Phase 3.1 显式延后(到下一阶段)

| 触点 | 现状 | 计划 |
|---|---|---|
| Pre-gen **澄清** queue (`text2sql_clarify_queue`) | 未实现 | 需要 graph 切到 `langgraph.StateGraph` 拿到 interrupt 分支 |
| Pre-exec **审批** queue (`text2sql_approval_queue`) + webhook | 未实现 | 同上;cost/cross-domain gate 依赖 OPA + Cube `/meta` 入栈 |
| Argilla → Langfuse 标注/审批操作日志同步 Loki | 未实现 | Promtail 已就绪,补 docker label 即可 |
| Argilla 角色 RBAC(annotator/approver/admin) | 默认三用户 quickstart 提供 | bootstrap 加 `--seed-users` 子命令(下迭代) |
| `text2sql_golden_v1` / `text2sql_adversarial_v1` 独立 dataset | 仅用反馈 dataset | 需要时再为评估集起独立 dataset |
| Argilla quickstart → 拆分生产部署(外置 PG/ES) | 仍 quickstart | 与 P4 Backstage 一道延后 |

### Phase 3.1 一次性首跑

```powershell
# 0) Phase 3 .env 再加(也可走默认):
#    ARGILLA_ENABLED=true
#    ARGILLA_API_KEY=owner.apikey
#    ARGILLA_WORKSPACE=admin
#    ARGILLA_DATASET=text2sql-feedback
#    EMBEDDING_DIM=384

cd text2sql-platform
.\make.cmd up-hitl                    # 起完整栈 + Argilla quickstart (~90s)
.\make.cmd argilla-bootstrap          # 幂等创建 schema (workspace + dataset + 6F/3Q/14M/1V)

# 1) 单测(本地 venv)
.\.venv\Scripts\python.exe -m pytest packages\contracts\tests services\langgraph-app\tests\unit\test_feedback.py tools\argilla\tests -v

# 2) 端到端(可选)
#  - Chainlit 提一个问题 → 点 ✏️ 给 corrected_sql
#  - Argilla UI http://localhost:6900 (owner / 12345678) 看 dataset 出现一条
#  - 在 UI 上把 metadata.reviewed 改为 true
.\make.cmd argilla-sync-golden        # 追加到 tests/eval/golden_set.yaml
.\make.cmd eval                       # 跑一次,校验新 case 通过
```
