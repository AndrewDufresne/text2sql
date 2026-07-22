# L6 — HITL 层(Human-in-the-Loop)

> 唯一组件:**Argilla**(`argilla/argilla-quickstart:latest`)
> 端口:`6900`
> 依赖:内置 Elasticsearch(quickstart 内)

---

## 1. 模块职责

承载 **三个 HITL 触点**:
1. **澄清(Pre-gen)**:模糊问题入"待澄清队列",由数据管家人审或回填术语
2. **审批(Pre-exec)**:高代价 / 跨域 SQL 进"待审批队列"
3. **反馈(Post-exec)**:用户 👎/修正 SQL 入"待标注队列",回流 Golden Set / Few-shot

---

## 2. 数据集设计(Argilla Datasets)

| Dataset | 用途 | Owner |
|---|---|---|
| `text2sql_feedback` | 用户反馈(👍/👎/修正 SQL) | 数据 SME |
| `text2sql_clarify_queue` | 待澄清(模糊提问) | 数据 SME + 业务 |
| `text2sql_approval_queue` | 待审批 SQL(高代价/跨域) | 数据管家 |
| `text2sql_golden_v1` | Golden Set(评估真值) | 数据 SME |
| `text2sql_adversarial_v1` | 对抗集 | 安全 + 红队 |

### 2.1 `text2sql_feedback` Record Schema
| 字段 | 类型 | 说明 |
|---|---|---|
| `id`(record id) | str(=trace_id) | 与 Langfuse 关联 |
| **fields** | | |
| `question` | text | 原问题(脱敏后) |
| `sql` | text(SQL) | 生成 SQL |
| `result_preview` | text | Top 5 行预览(脱敏) |
| `explanation` | text | NL 解释 |
| **metadata** | | |
| `user_role`、`business_unit`、`model`、`prompt_version`、`tables_used[]`、`metrics_used[]`、`cost_usd`、`latency_ms` | | |
| **vectors** | | |
| `question` | float[1024] | bge-m3 |
| **questions(响应表单)** | | |
| `thumb` | label `{up,down}` | 必填 |
| `corrected_sql` | text | 选填 |
| `failure_mode` | label `{wrong_metric, wrong_join, wrong_filter, hallucination, perf, other}` | 选填 |

---

## 3. 输入输出约束

### 3.1 LangGraph → Argilla(写入)

每次成功/失败响应都写一条 `text2sql_feedback`,初始无 `responses`。

```python
rg.Record(
  id=trace_id,
  fields={...}, metadata={...}, vectors={"question": emb}
)
```
约束:
- 字段值已经过 Presidio 脱敏(原始值不出现)
- `metadata` 与 Langfuse trace 字段保持**字段名完全一致**(便于联表)

### 3.2 Argilla → LangGraph App(回流)

通过 Argilla SDK 拉取 `status=submitted` 记录,转换为 Promptfoo YAML 用例:
```yaml
- vars: { question: "..." }
  assert:
    - type: exec_sql_match
      value: "<corrected_sql>"
```

约束:
- 仅 `corrected_sql` 经过 SME 二次确认(`metadata.reviewed=true`)的才入 Golden Set
- 入集后回填 Argilla `metadata.golden_set_id`

### 3.3 Argilla 内部权限

| 角色 | 权限 |
|---|---|
| `annotator`(数据 SME) | 标注 `feedback`、`clarify_queue` |
| `approver`(数据管家) | 审批 `approval_queue` |
| `admin`(平台) | 全部 + 创建数据集 |

---

## 4. 工作流(BPMN 简版)

```
反馈闭环:
  user 👎 → LangGraph → Argilla feedback (status=pending)
        → SME review → submit (corrected_sql, failure_mode)
        → Promptfoo Golden Set PR(自动 / 手动)
        → CI eval pass → merge → 上线监控收敛

审批闭环:
  LangGraph 检测 cost>阈值 / 跨敏感域
        → 阻塞执行 → Argilla approval (status=pending)
        → approver decide → Argilla webhook → LangGraph 恢复执行 / 拒答

澄清闭环:
  LangGraph 意图模糊 → Chainlit 直接弹澄清(同步)
        失败 N 次 → 入 Argilla clarify_queue(异步)→ SME 完善术语词典
```

---

## 5. 安全约束

- 仅写脱敏数据;原始 PII 永不入 Argilla
- 标注台不可执行 SQL(只读展示);避免 SME 当 RM 用
- 审计:Argilla 操作日志同步 Loki(标注/审批人 + 时间)

---

## 6. 测试策略

### 契约
- `text2sql_feedback` schema(JSON Schema 化) → 任何字段缺失立刻 fail
- Argilla SDK 调用封装的 mock 测试

### 集成
- Testcontainers 拉 `argilla-quickstart` → 写入/读取一条 record
- Webhook(approval)端到端

### E2E
- UI 点 👎 + 提交修正 SQL → Argilla `text2sql_feedback` 出现 record
- 高代价 SQL → `approval_queue` 出现 → approver 通过 → LangGraph 完成执行

### 安全
- 注入字符串作为 `corrected_sql` → 入库前必须再过 sqlglot 校验

---

## 7. 待确认

- 标注台是否需要"批量标注"工作流(SME 一次审 50 条)?
- approval 是否设 SLA(如 5 分钟无人审 → 自动拒)?
- Golden Set 入集后,是否反向"修复"Few-shot 库?
