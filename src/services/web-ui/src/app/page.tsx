"use client";

import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Composer } from "@/components/Composer";
import { MessageList } from "@/components/MessageList";
import { EmptyState } from "@/components/EmptyState";
import { GlossaryDrawer } from "@/components/GlossaryDrawer";
import { CapabilityDrawer } from "@/components/CapabilityDrawer";
import {
  appendMessage,
  createThread,
  listMessages,
  listThreads,
  postQuery,
  renameThread,
} from "@/lib/api";
import { PILOT_USER } from "@/lib/config";
import type { ChatMessage, ChatThread, QueryResponse } from "@/lib/types";

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function defaultTitle(question: string): string {
  const t = question.trim().replace(/\s+/g, " ");
  return t.length > 60 ? t.slice(0, 57) + "…" : t;
}

/** Dedupe by id, preserve last occurrence (newer payload wins). */
function dedupeById(items: ChatMessage[]): ChatMessage[] {
  const seen = new Map<number, ChatMessage>();
  for (const m of items) seen.set(m.id, m);
  return Array.from(seen.values());
}

export default function Home() {
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [optimisticUser, setOptimisticUser] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showGlossary, setShowGlossary] = useState(false);
  const [showCapabilities, setShowCapabilities] = useState(false);

  const refreshThreads = useCallback(async () => {
    try {
      const t = await listThreads(PILOT_USER);
      setThreads(t);
      return t;
    } catch (e) {
      console.warn("listThreads failed", e);
      return [];
    }
  }, []);

  useEffect(() => {
    refreshThreads();
  }, [refreshThreads]);

  // Load messages when active thread changes
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    listMessages(PILOT_USER, activeId)
      .then((items) => {
        if (cancelled) return;
        setMessages(dedupeById(items));
      })
      .catch((e) => {
        if (cancelled) return;
        console.warn("listMessages failed", e);
        setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const onNewThread = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setError(null);
  }, []);

  const onSelectThread = useCallback((id: string) => {
    setActiveId(id);
    setError(null);
  }, []);

  const onAsk = useCallback(
    async (question: string) => {
      if (!question.trim() || pending) return;
      setError(null);
      setPending(true);
      setOptimisticUser(question);
      try {
        // Create a thread on first turn
        let tid = activeId;
        let thread: ChatThread | null = null;
        if (!tid) {
          thread = await createThread(PILOT_USER, defaultTitle(question));
          tid = thread.id;
          setActiveId(tid);
          setThreads((prev) => [thread!, ...prev]);
        }

        // Persist the user turn first so a refresh shows it.
        const userMsg = await appendMessage(PILOT_USER, tid, {
          role: "user",
          content: question,
        });
        setMessages((prev) => dedupeById([...prev, userMsg]));
        setOptimisticUser(null);

        // Call the assistant
        const traceId = uuid();
        const resp: QueryResponse = await postQuery({
          trace_id: traceId,
          user: PILOT_USER,
          session_id: tid,
          question,
        });

        // Persist the assistant turn
        const assistantContent =
          resp.explanation ||
          (resp.error ? `Error: ${resp.error.message}` : "(no answer)");
        const aMsg = await appendMessage(PILOT_USER, tid, {
          role: "assistant",
          content: assistantContent,
          query_id: resp.trace_id,
          payload: resp,
        });
        setMessages((prev) => dedupeById([...prev, aMsg]));

        // Auto-rename thread to the question if still default
        if (thread && thread.title === defaultTitle(question)) {
          // already correct
        }
        // Bump the thread to top
        refreshThreads();
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
      } finally {
        setPending(false);
        setOptimisticUser(null);
      }
    },
    [activeId, pending, refreshThreads],
  );

  const onRename = useCallback(
    async (id: string, title: string) => {
      try {
        await renameThread(PILOT_USER, id, title);
        refreshThreads();
      } catch (e) {
        console.warn("rename failed", e);
      }
    },
    [refreshThreads],
  );

  const empty = messages.length === 0 && !optimisticUser && !pending;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg text-fg">
      <Sidebar
        threads={threads}
        activeId={activeId}
        onSelect={onSelectThread}
        onNew={onNewThread}
        onRename={onRename}
        onOpenGlossary={() => setShowGlossary(true)}
        onOpenCapabilities={() => setShowCapabilities(true)}
        onRefresh={refreshThreads}
      />
      <main className="flex-1 flex flex-col min-w-0">
        <Header
          title={
            activeId
              ? threads.find((t) => t.id === activeId)?.title || "Conversation"
              : "New conversation"
          }
        />
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {empty ? (
            <EmptyState onPick={onAsk} onOpenGlossary={() => setShowGlossary(true)} />
          ) : (
            <MessageList
              messages={messages}
              optimisticUser={optimisticUser}
              pending={pending}
              error={error}
            />
          )}
        </div>
        <Composer onSend={onAsk} disabled={pending} />
      </main>
      <GlossaryDrawer open={showGlossary} onClose={() => setShowGlossary(false)} />
      <CapabilityDrawer
        open={showCapabilities}
        onClose={() => setShowCapabilities(false)}
      />
    </div>
  );
}
