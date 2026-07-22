# Text2SQL Platform — 汇报演示（PPT 风格静态网页）

一个**本地化、即开即用**的静态 React 单页演示，用于向管理者讲清楚：
项目解决的痛点、8 层架构，以及**一个终端用户的问题如何依次通过
权限检查 → 语义解析 → 组织 SQL → 语法校验 → 执行 → 结果分析**，
以及各中间件的使命与全链路的透明可观测。

面向非技术读者：正文中的英文缩写（SQL / PII / OPA / AST / RM / SLO …）
均在首次出现处用括号补充中文全称。

## 两个版本（共用 `vendor/`）

| 文件 | 语言 | 打开方式 |
|---|---|---|
| [`index.html`](index.html) | 中文 | 双击 |
| [`index.en.html`](index.en.html) | English（完全英文版） | 双击 |

**一键切换语言**：任一版本右下角都有 `中文 / EN` 开关（或按 `T`），点击即跳到另一语言、
并**停留在当前同一页**（通过 URL `#页码` 记忆位置）。两个文件需放在同一目录。

## 运行方式

**直接双击 `index.html`（中文）或 `index.en.html`（English）** 即可（无需构建、无需服务器、无需联网）。

React / ReactDOM / Babel 已 vendored 到 `./vendor/`，页面 100% 离线运行。
如需通过本地服务器打开（部分浏览器对 `file://` 更严格）：

```powershell
# 任选其一
python -m http.server 8090     # 然后访问 http://localhost:8090
npx serve .
```

## 操作

| 按键 | 作用 |
|---|---|
| `←` / `→` / 空格 | 上一页 / 下一页 |
| `Home` / `End` | 首页 / 末页 |
| `O` | 打开/关闭目录（可跳转任意页） |
| `F` | 全屏演示 |
| `T` | 中文 / EN 一键切换（保持当前页） |

右下角也有 `‹ ›`、`中文/EN`、`目录`、`全屏` 按钮。

## 设计

- 视觉：金融商务风格（红/白/灰、六边形标识、克制留白、细分隔线）。
- 内容严格对应本仓库实现：`app/graph.py` 的 9 节点管道、
  `nodes/*.py`、`config/opa/policies/text2sql.rego`、`schema_catalog.py`、
  `config/litellm/config.yaml`（DeepSeek‑V3）、`docs/Architecture.md`。

## 文件

```
presentation/
├── index.html      # 中文版（金融商务风格 + 19 页 React 幻灯片）
├── index.en.html   # English 版（同结构、完全英文）
├── README.md
└── vendor/         # 离线运行所需（React 18 · ReactDOM · Babel standalone）
```

> 模型统一表述为 **OpenAI GPT**。“七步旅程总览”页已重做为逐步可读的流程图。
