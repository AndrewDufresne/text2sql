# Text2SQL Platform

企业级 Text-to-SQL 平台 — 让 RM、风险、合规、运营、Finance 等角色用**自然语言**
安全、准确、可审计地查询银行数据。

**Powered by DeepSeek API · 8-layer architecture · 7-node pipeline · 11 containers.**

---

## 快速开始

### 前置条件

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (≥ 26.x)
- [DeepSeek API Key](https://platform.deepseek.com/api_keys) (免费注册即可)

### 1. 克隆 & 配置

```powershell
git clone git@github.com:AndrewDufresne/text2sql.git
cd text2sql-platform

# 编辑 .env，填入你的 DeepSeek API Key
notepad .env
```

### 2. 启动

```powershell
# 完整启动（首次需拉取镜像 + 构建应用，约 3–5 分钟）
.\t2sql.ps1 start min

# 或使用 Make（Git Bash / WSL）
make up-min
```

### 3. 验证

```powershell
# 健康检查
.\t2sql.ps1 health

# 打开主界面
start http://localhost:3203
```

问一个问题试试：*"How many active clients are there?"*

---

## 架构概览

```
User Question
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│ L7 体验层    web-ui (Next.js 15)     http://localhost:3203   │
├──────────────────────────────────────────────────────────────┤
│ L5 编排层    langgraph-app (FastAPI)  http://localhost:8080  │
│              │                                               │
│              ├─ pii_guard      PII 检测 · 注入拦截           │
│              ├─ schema_link    pgvector + TEI 语义检索       │
│              ├─ sql_generate   LiteLLM → DeepSeek 生成 SQL   │
│              ├─ sql_validate   sqlglot AST 校验 · 白名单     │
│              ├─ opa_check      Rego 策略 · 表级授权           │
│              ├─ execute        Trino 查询 · 身份穿透          │
│              ├─ explain        NL 自然语言解释                │
│              └─ output_mask    Presidio 出口 PII 脱敏         │
├──────────────────────────────────────────────────────────────┤
│ L4 能力层    LiteLLM · TEI · Presidio · sqlglot · OPA        │
│ L3 知识层    pgvector (语义向量检索)                          │
│ L2 执行层    Trino 442 (SQL 查询引擎)                        │
│ L1 平台层    Langfuse (Trace / Prompt / Eval)                │
│ L0 治理层    Prometheus · Grafana · Loki · Tempo (可选)      │
└──────────────────────────────────────────────────────────────┘
```

## 服务拓扑 (默认栈 — 11 个容器)

| 容器 | 端口 | 用途 |
|---|---|---|
| `t2sql-pg-platform` | 5432 | PostgreSQL — Langfuse 元数据 + 聊天持久化 |
| `t2sql-pg-cib` | 5433 | PostgreSQL + pgvector — 业务数据 + 语义索引 |
| `t2sql-litellm` | 4000 | LiteLLM 网关 → DeepSeek API |
| `t2sql-langfuse` | 3202 | LLM 可观测性 (Trace / Prompt / Eval) |
| `t2sql-trino` | 8081 | Trino SQL 查询引擎 |
| `t2sql-presidio-analyzer` | 5001 | Microsoft Presidio — PII 检测 |
| `t2sql-presidio-anonymizer` | 5002 | Microsoft Presidio — PII 脱敏 |
| `t2sql-tei-embed` | 8082 | HuggingFace TEI — 文本嵌入 (bge-small-en-v1.5) |
| `t2sql-opa` | 8181 | Open Policy Agent — 策略鉴权 |
| `t2sql-langgraph` | 8080 | 核心 API (FastAPI) — 7 节点管道 |
| `t2sql-web-ui` | 3203 | 用户界面 (Next.js 15 + React 19) |

### 可访问地址

| 服务 | URL | 凭据 |
|---|---|---|
| **Web UI (主界面)** | http://localhost:3203 | 无需登录 (Pilot) |
| **Langfuse (Trace)** | http://localhost:3202 | `admin@t2sql.local` / `admin_dev_only` |
| **LangGraph API** | http://localhost:8080 | OpenAPI: `/docs` · Metrics: `/metrics` |
| **LiteLLM** | http://localhost:4000 | — |

### 可选扩展栈

| 栈 | 命令 | 说明 |
|---|---|---|
| 可观测性 (LGTM) | `make up-obs` | Prometheus + Grafana + Loki + Tempo |
| 容器管理 | `make up-portal` | Portainer CE |
| HITL 反馈 | `make up-hitl` | Argilla 人工标注 |
| 数据目录 | `make up-datahub` | DataHub 数据血缘/术语 |

---

## 常用命令

```powershell
# PowerShell (推荐)
.\t2sql.ps1 start min    # 启动默认栈
.\t2sql.ps1 stop         # 停止所有容器
.\t2sql.ps1 status       # 查看容器状态
.\t2sql.ps1 health       # 健康检查
.\t2sql.ps1 logs         # 查看日志
.\t2sql.ps1 urls         # 打印所有服务地址
.\t2sql.ps1 doctor       # 环境预检

# Make (Git Bash / WSL)
make up-min              # 启动默认栈
make down-min            # 停止 (保留数据卷)
make ps                  # 容器状态
make health              # 健康检查
make smoke-trino         # Trino 数据验证
make test                # 运行所有测试
```

---

## 项目结构

```
text2sql-platform/
├── compose/                    # Docker Compose 分层文件
│   ├── 00-network.yml          #   共享网络 (默认栈)
│   ├── 10-state.yml            #   PostgreSQL × 2 (默认栈)
│   ├── 20-platform.yml         #   LiteLLM + Langfuse (默认栈)
│   ├── 30-data.yml             #   Trino (默认栈)
│   ├── 40-capability.yml       #   Presidio + TEI + OPA (默认栈)
│   ├── 50-app.yml              #   langgraph-app + web-ui (默认栈)
│   ├── 31-datahub.yml          #   DataHub (可选)
│   ├── 60-hitl.yml             #   Argilla (可选)
│   ├── 70-observability.yml    #   Prom + Grafana + Loki + Tempo (可选)
│   └── 80-portal.yml           #   Portainer (可选)
├── config/                     # 服务配置文件
│   ├── litellm/config.yaml     #   LiteLLM 模型路由
│   ├── opa/policies/           #   Rego 授权策略
│   ├── postgres-cib/init/      #   数据库种子 SQL
│   ├── trino/etc/              #   Trino 配置
│   └── ...
├── src/packages/contracts/         # Python 共享契约 (Pydantic v2)
├── src/services/
│   ├── langgraph-app/          # 核心后端 (FastAPI + 管道)
│   │   ├── app/
│   │   │   ├── nodes/          #   7 个管道节点
│   │   │   ├── clients/        #   外部服务客户端
│   │   │   ├── graph.py        #   管道编排器
│   │   │   └── schema_catalog.py # 表 Schema 定义
│   │   └── tests/              #   单元测试 (115 passed)
│   └── web-ui/                 # 前端 (Next.js 15 + React 19)
├── scripts/                    # 部署脚本 (Ubuntu 服务器)
├── tests/                      # E2E + Eval 测试
├── docs/                       # 架构文档 · ADR · 层设计
├── .env.example                # 环境变量模板
├── t2sql.ps1                   # PowerShell 控制脚本 (推荐)
├── Makefile / make.cmd         # Make 构建脚本
└── README.md
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| **LLM** | DeepSeek-V3 via LiteLLM (OpenAI 兼容协议) |
| **后端** | Python 3.11 · FastAPI · asyncpg · httpx |
| **前端** | Next.js 15 · React 19 · Tailwind CSS 3.4 |
| **查询引擎** | Trino 442 (PostgreSQL connector) |
| **向量检索** | pgvector (pg16) · HNSW 索引 · TEI (bge-small-en-v1.5) |
| **安全** | sqlglot AST 校验 · OPA Rego 策略 · Presidio PII 脱敏 |
| **可观测** | Langfuse v2 · Prometheus · Grafana (可选) |
| **部署** | Docker Compose (11 容器) |

---

## 测试

```powershell
# 全部单元测试 + 契约测试 (115 项)
make test

# 仅单元测试
cd src/services/langgraph-app && python -m pytest -m "not e2e" -v

# E2E 测试 (需要栈在线)
make test-e2e
```

---

## 文档

- [架构设计](docs/Architecture.md) — 8 层架构 · 数据流 · 安全模型 · SLO
- [I/O 契约](docs/contracts/io-contracts.md) — 15 项跨层契约 (C1–C15)
- [ADR](docs/adr/) — 架构决策记录 (0001–0006)
- [各层设计](docs/layers/) — L0 治理 → L7 体验
- [变更日志](docs/CHANGELOG.md)
- [项目介绍页](docs/project-intro.html) — 可视化项目全景

---

## 部署到服务器

```powershell
# 将源码 + Docker 镜像推送到 Ubuntu 服务器 (192.168.125.18)
.\scripts\deploy-to-ubuntu.ps1
```

服务器端使用 `.env.server` 覆盖端口映射以避免与现有服务冲突。
