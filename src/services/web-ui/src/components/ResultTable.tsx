"use client";

import { Download } from "lucide-react";
import { useMemo } from "react";
import type { QueryResult } from "@/lib/types";

interface Props {
  result: QueryResult;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function toCsv(result: QueryResult): string {
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [result.columns.join(",")];
  for (const row of result.rows) {
    lines.push(row.map(escape).join(","));
  }
  return lines.join("\n");
}

export function ResultTable({ result }: Props) {
  const csvHref = useMemo(() => {
    const blob = new Blob([toCsv(result)], { type: "text/csv" });
    return URL.createObjectURL(blob);
  }, [result]);

  return (
    <div className="rounded-lg border border-border overflow-hidden bg-bg">
      <div className="flex items-center justify-between border-b border-border bg-bg-subtle px-3 py-2">
        <div className="text-xs text-fg-muted">
          {result.row_count.toLocaleString()} row{result.row_count === 1 ? "" : "s"}
          {result.truncated && " (truncated)"}
        </div>
        <a
          href={csvHref}
          download="result.csv"
          className="flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
        >
          <Download size={12} /> CSV
        </a>
      </div>
      <div className="max-h-[420px] overflow-auto scrollbar-thin">
        <table className="result-table">
          <thead>
            <tr>
              {result.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="font-mono text-[13px]">
                    {fmt(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
