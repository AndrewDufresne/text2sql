"use client";

import { Activity, Clock, DollarSign, Shield } from "lucide-react";
import type { QueryResponse } from "@/lib/types";

interface Props {
  payload: QueryResponse;
}

export function ResponseFooter({ payload }: Props) {
  const masked = payload.output_mask?.cells_masked ?? 0;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-fg-subtle">
      {payload.model && (
        <span className="flex items-center gap-1">
          <Activity size={11} /> {payload.model}
          {payload.prompt_version && ` · ${payload.prompt_version}`}
        </span>
      )}
      {typeof payload.latency_ms === "number" && (
        <span className="flex items-center gap-1">
          <Clock size={11} /> {payload.latency_ms} ms
        </span>
      )}
      {typeof payload.cost_usd === "number" && payload.cost_usd > 0 && (
        <span className="flex items-center gap-1">
          <DollarSign size={11} /> ${payload.cost_usd.toFixed(4)}
        </span>
      )}
      {masked > 0 && (
        <span
          className="flex items-center gap-1 text-warn"
          title={JSON.stringify(payload.output_mask?.entity_counts)}
        >
          <Shield size={11} /> {masked} cell{masked === 1 ? "" : "s"} masked
        </span>
      )}
      {payload.tables_used && payload.tables_used.length > 0 && (
        <span className="truncate">tables: {payload.tables_used.join(", ")}</span>
      )}
      <span className="font-mono opacity-60">trace {payload.trace_id.slice(0, 8)}</span>
    </div>
  );
}
