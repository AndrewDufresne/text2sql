# L7 — 体验层(Experience)

> 唯一组件:**Chainlit Web Chat UI**
> 部署:`python:3.11-slim` + `chainlit` 自建镜像
> 端口:`8000`

---

## 1. 模块职责

- 唯一面向最终用户(RM/分析师/合规)的入口
- 输入:自然语言提问、澄清回答、👍/👎/修正 SQL
- 输出:流式回复、结构化结果(表格)、引用(SQL/口径/字段)

---

## 2. 模块边界与依赖

| 边界 | 协议 | 说明 |
|---|---|---|
| **上游** Browser → Chainlit | HTTPS + WebSocket | Cookie session(Phase 1 假账户;Phase 2 OIDC SSO) |
| **下游** Chainlit → LangGraph App | HTTP `POST /api/v1/query`、`POST /api/v1/feedback` | 见 [C2](../contracts/io-contracts.md#c2-chainlit--langgraph-app) |
| **平台** Chainlit → Langfuse | SDK(可选) | 仅记录 UI 侧事件(打开/会话开始) |
| **平台** Chainlit → OTel | OTLP HTTP | session/click/页面级 trace |

---

## 3. UI 信息架构

```
┌──────────────────────────────────────────────┐
│ Header: 用户/角色 · 当前业务域 · 帮助           │
├──────────────────────────────────────────────┤
│ Chat 流                                        │
│  ┌───────────────────────────────────────┐    │
│  │ 用户消息                              │    │
│  ├───────────────────────────────────────┤    │
│  │ 助手回复(流式)                       │    │
│  │  ├ 自然语言解释                       │    │
│  │  ├ 结果表(可下载 CSV)                │    │
│  │  ├ 引用块:SQL · 口径 · 表/列 · 模型版本│    │
│  │  └ 反馈条:👍 👎 修正 SQL  trace_id 复制 │    │
│  └───────────────────────────────────────┘    │
├──────────────────────────────────────────────┤
│ 输入框 · "@cube measure" · "@table" 触发提示  │
└──────────────────────────────────────────────┘
```

---

## 4. 输入输出约束

### 4.1 用户输入(浏览器→Chainlit)
- 文本:UTF-8,长度 ≤ 2000 字符;超出客户端拦截
- 文件上传:**Phase 1 不开**(避免数据外发)
- 反馈:`thumb ∈ {up,down}`,可选 `corrected_sql`(<= 5000 chars)

### 4.2 透传到 LangGraph(C2 契约)
Chainlit 必须从 session 注入:
- `trace_id`(每请求新生成 UUIDv7)
- `user.{id, role, business_unit}`
- `session_id`

> **强制**:Chainlit 不直接调 LiteLLM / Cube / Trino;一切走 LangGraph。

### 4.3 显示约束
- 结果表 > `row_limit`(默认 1000)→ 显示截断提示 + 下载完整 CSV 按钮
- 错误 → 红条 + `trace_id` 复制按钮 + "联系数据团队"链接
- 高风险待审批 → 黄条 + 审批人姓名 + 等待状态

---

## 5. 安全约束

- 不在前端拼任何 SQL,所有 SQL 由 LangGraph 返回
- `trace_id` 与 `user_id` 不放 URL,只放 header / body
- CSP:`default-src 'self'`;禁止外链 JS
- 反馈接口需 CSRF token
- Phase 1 鉴权:HTTP Basic + 配置文件用户;Phase 2 接 SSO/OIDC

---

## 6. 测试策略

### 契约
- C2 请求 schema:断言所有字段、边界值、必填漏填

### 单元
- 用户输入校验(长度/编码/特殊字符)
- 反馈表单编码

### E2E(Playwright)
1. 登录 → 提问 → 看到流式回复 + 表格 + 引用块
2. 点 👎 → 弹 "修正 SQL" → 提交 → 提示已记录(Argilla 出现 record)
3. 提问越权 → 看到红条 + trace_id 可复制
4. 网络断开 → 重连后会话保持

### 可观测性
- 每个会话至少一条 OTel session span
- 反馈点击 → metric `text2sql_ui_feedback_total{thumb="down"}` +1

---

## 7. 待确认

- UI 是否需要中文界面? — 假设支持中英切换
- 是否需要导出"问题+SQL+结果"完整 PDF(合规留痕)?
- 历史会话保留期(浏览器 vs 后端)?
