# CIB Text-to-SQL Assistant — Web UI

Next.js 15 + React 19 chat interface for the **CIB Text-to-SQL Assistant**
(codename Atlas). Talks to `langgraph-app` via same-origin rewrites — there is
no client-side CORS exposure and no backend secret reaches the browser.

## Local dev

```bash
npm install
LANGGRAPH_URL=http://localhost:8080 npm run dev
# open http://localhost:3030
```

## Container

Built from this directory by `compose/50-app.yml` as service `web-ui`.
The image is a multi-stage `node:20` build using Next.js `output: "standalone"`
so the runtime layer ships without `node_modules`.

## Architecture

- `src/app/page.tsx` — main shell: sidebar + header + message list + composer
- `src/components/Sidebar.tsx` — thread list, capability/glossary drawers
- `src/components/EmptyState.tsx` — curated examples loaded from
  `GET /api/v1/examples`
- `src/components/AssistantBubble.tsx` — table-first answer, then prose, then
  collapsible SQL, then footer (model · latency · cost · masked-cells · trace)
- `src/lib/api.ts` — typed REST client; same-origin via Next.js rewrites
- `src/lib/theme.tsx` — light / dark / **system** (default) theme

## Environment

| Var | Purpose | Default |
|---|---|---|
| `LANGGRAPH_URL` | Upstream API used by the rewrite proxy | `http://langgraph-app:8080` |
| `NEXT_PUBLIC_PILOT_USER_ID` | Pilot user identity until SSO | `alice@bank` |
| `NEXT_PUBLIC_PILOT_USER_ROLE` | RBAC role passed to OPA | `RM` |
| `NEXT_PUBLIC_PILOT_BUSINESS_UNIT` | Tenant filter for OPA / Cube | `CIB-APAC` |
| `NEXT_PUBLIC_APP_VERSION` | Shown in the sidebar | `1.0.0-rc1` |
