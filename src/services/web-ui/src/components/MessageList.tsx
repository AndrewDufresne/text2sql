"use client";

import type { ChatMessage } from "@/lib/types";
import { UserBubble } from "./UserBubble";
import { AssistantBubble } from "./AssistantBubble";
import { Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";

interface Props {
  messages: ChatMessage[];
  optimisticUser: string | null;
  pending: boolean;
  error: string | null;
}

export function MessageList({ messages, optimisticUser, pending, error }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, optimisticUser, pending]);

  return (
    <div className="mx-auto max-w-3xl px-5 py-6 space-y-6">
      {messages.map((m, i) =>
        m.role === "user" ? (
          <UserBubble key={`u-${m.id}-${i}`} content={m.content} />
        ) : (
          <AssistantBubble
            key={`a-${m.id}-${i}`}
            content={m.content}
            payload={m.payload}
          />
        ),
      )}
      {optimisticUser && <UserBubble content={optimisticUser} />}
      {pending && (
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          <Loader2 size={14} className="animate-spin" />
          <span>Planning, generating SQL, and executing on Trino…</span>
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
