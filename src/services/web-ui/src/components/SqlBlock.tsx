"use client";

import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import { useState } from "react";

interface Props {
  sql: string;
}

export function SqlBlock({ sql }: Props) {
  const [open, setOpen] = useState(true);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="rounded-lg border border-border bg-bg-subtle">
      <div className="flex items-center justify-between px-3 py-1.5">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          Generated SQL
        </button>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {open && (
        <pre className="overflow-x-auto px-3 pb-3 pt-0 text-[12.5px] font-mono leading-6 text-fg">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  );
}
