import type {
  Capabilities,
  ChatMessage,
  ChatThread,
  ExampleItem,
  GlossaryItem,
  QueryRequest,
  QueryResponse,
  UserCtx,
} from "./types";

// Same-origin in browser (Next.js rewrites /api/v1/* → langgraph-app).
// SSR / build can override via NEXT_PUBLIC_API_BASE.
const BASE =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_BASE || ""
    : "";

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
  return (await r.json()) as T;
}

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${path} → HTTP ${r.status}: ${text.slice(0, 200)}`);
  }
  return (await r.json()) as T;
}

async function jpatch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
  return (await r.json()) as T;
}

async function jdel(path: string): Promise<void> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) throw new Error(`${path} → HTTP ${r.status}`);
}

// ---- query ----
export async function postQuery(req: QueryRequest): Promise<QueryResponse> {
  return jpost<QueryResponse>("/api/v1/query", req);
}

// ---- capability surface ----
export async function getGlossary(q?: string): Promise<GlossaryItem[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  const data = await jget<{ items: GlossaryItem[] }>(`/api/v1/glossary${qs}`);
  return data.items;
}

export async function getExamples(): Promise<ExampleItem[]> {
  const data = await jget<{ items: ExampleItem[] }>("/api/v1/examples");
  return data.items;
}

export async function getCapabilities(): Promise<Capabilities> {
  return jget<Capabilities>("/api/v1/capabilities");
}

// ---- threads ----
export async function listThreads(user: UserCtx): Promise<ChatThread[]> {
  const data = await jget<{ items: ChatThread[] }>(
    `/api/v1/threads?user_id=${encodeURIComponent(user.id)}`,
  );
  return data.items;
}

export async function createThread(
  user: UserCtx,
  title: string,
): Promise<ChatThread> {
  return jpost<ChatThread>("/api/v1/threads", { user_id: user.id, title });
}

export async function renameThread(
  user: UserCtx,
  id: string,
  title: string,
): Promise<void> {
  await jpatch(
    `/api/v1/threads/${id}?user_id=${encodeURIComponent(user.id)}`,
    { title },
  );
}

export async function deleteThread(user: UserCtx, id: string): Promise<void> {
  await jdel(`/api/v1/threads/${id}?user_id=${encodeURIComponent(user.id)}`);
}

export async function listMessages(
  user: UserCtx,
  threadId: string,
): Promise<ChatMessage[]> {
  const data = await jget<{ items: ChatMessage[] }>(
    `/api/v1/threads/${threadId}/messages?user_id=${encodeURIComponent(user.id)}`,
  );
  return data.items;
}

export async function appendMessage(
  user: UserCtx,
  threadId: string,
  msg: {
    role: "user" | "assistant" | "system";
    content: string;
    query_id?: string;
    payload?: unknown;
  },
): Promise<ChatMessage> {
  return jpost<ChatMessage>(
    `/api/v1/threads/${threadId}/messages?user_id=${encodeURIComponent(user.id)}`,
    msg,
  );
}
