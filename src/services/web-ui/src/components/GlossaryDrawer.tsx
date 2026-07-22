"use client";

import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getGlossary } from "@/lib/api";
import type { GlossaryItem } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function GlossaryDrawer({ open, onClose }: Props) {
  const [items, setItems] = useState<GlossaryItem[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getGlossary()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [open]);

  const filtered = useMemo(() => {
    if (!q.trim()) return items;
    const needle = q.toLowerCase();
    return items.filter(
      (i) =>
        i.term.toLowerCase().includes(needle) ||
        i.definition.toLowerCase().includes(needle),
    );
  }, [items, q]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-[420px] max-w-full flex-col border-l border-border bg-bg shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold">Business glossary</div>
            <div className="text-[11px] text-fg-subtle">
              Terms the assistant understands and how it interprets them.
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1.5 hover:bg-bg-muted text-fg-muted"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        <div className="border-b border-border px-3 py-2">
          <div className="flex items-center gap-2 rounded-md border border-border bg-bg-subtle px-2 py-1.5">
            <Search size={14} className="text-fg-subtle" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search terms…"
              className="flex-1 bg-transparent text-sm outline-none placeholder:text-fg-subtle"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-2">
          {loading && <div className="p-3 text-sm text-fg-muted">Loading…</div>}
          {!loading && filtered.length === 0 && (
            <div className="p-3 text-sm text-fg-muted">No terms match.</div>
          )}
          <ul className="divide-y divide-border">
            {filtered.map((g) => (
              <li key={g.term} className="py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <div className="text-sm font-medium text-fg">{g.term}</div>
                  <div className="text-[10px] uppercase tracking-wider text-fg-subtle">
                    {g.source}
                  </div>
                </div>
                <div className="mt-1 text-[13px] leading-6 text-fg-muted">
                  {g.definition}
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
