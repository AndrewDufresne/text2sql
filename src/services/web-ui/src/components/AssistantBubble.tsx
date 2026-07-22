"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ResultTable } from "./ResultTable";
import { SqlBlock } from "./SqlBlock";
import { ResponseFooter } from "./ResponseFooter";
import type { QueryResponse } from "@/lib/types";

interface Props {
  content: string;
  payload: QueryResponse | null;
}

export function AssistantBubble({ content, payload }: Props) {
  return (
    <div className="flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">
        A
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {/* Refusal / error banner */}
        {payload?.status === "refused" && (
          <div className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn">
            Request refused by policy: {payload.error?.message ?? "not allowed"}
          </div>
        )}
        {payload?.status === "error" && payload.error && (
          <div className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {payload.error.code}: {payload.error.message}
          </div>
        )}

        {/* Result table first — that's the primary answer */}
        {payload?.result && payload.result.row_count > 0 && (
          <ResultTable result={payload.result} />
        )}
        {payload?.result && payload.result.row_count === 0 && (
          <div className="rounded-lg border border-border bg-bg-subtle px-3 py-2 text-sm text-fg-muted">
            Query returned 0 rows.
          </div>
        )}

        {/* Explanation */}
        <div className="prose-app">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>

        {/* SQL */}
        {payload?.sql && <SqlBlock sql={payload.sql} />}

        {/* Footer (model, latency, cost, trace) */}
        {payload && <ResponseFooter payload={payload} />}
      </div>
    </div>
  );
}
