"use client";

import {
  BookOpen,
  ChevronRight,
  MessageSquarePlus,
  MoreHorizontal,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import type { ChatThread } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";
import { PRODUCT_NAME, PRODUCT_VERSION, PILOT_USER } from "@/lib/config";

interface Props {
  threads: ChatThread[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onOpenGlossary: () => void;
  onOpenCapabilities: () => void;
  onRefresh: () => void;
}

export function Sidebar({
  threads,
  activeId,
  onSelect,
  onNew,
  onRename,
  onOpenGlossary,
  onOpenCapabilities,
  onRefresh,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  if (collapsed) {
    return (
      <aside className="flex h-full w-12 flex-col items-center border-r border-border bg-bg-subtle py-3 gap-2">
        <button
          onClick={() => setCollapsed(false)}
          aria-label="Expand sidebar"
          className="rounded p-2 hover:bg-bg-muted text-fg-muted"
        >
          <ChevronRight size={18} />
        </button>
        <button
          onClick={onNew}
          aria-label="New chat"
          className="rounded p-2 hover:bg-bg-muted text-fg-muted"
        >
          <MessageSquarePlus size={18} />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-bg-subtle">
      {/* Brand */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-accent-fg font-semibold text-sm">
            A
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold truncate">{PRODUCT_NAME}</div>
            <div className="text-[11px] text-fg-subtle">{PRODUCT_VERSION}</div>
          </div>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="rounded p-1.5 hover:bg-bg-muted text-fg-muted"
          aria-label="Collapse sidebar"
        >
          <ChevronRight size={16} className="rotate-180" />
        </button>
      </div>

      {/* New chat */}
      <div className="px-3 pt-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-md border border-border bg-bg px-3 py-2 text-sm hover:bg-bg-muted transition"
        >
          <MessageSquarePlus size={16} />
          <span>New conversation</span>
        </button>
      </div>

      {/* Threads */}
      <div className="mt-4 flex items-center justify-between px-4 text-[11px] uppercase tracking-wider text-fg-subtle">
        <span>Recent</span>
        <button
          onClick={onRefresh}
          className="rounded p-1 hover:bg-bg-muted"
          aria-label="Refresh threads"
        >
          <RefreshCcw size={12} />
        </button>
      </div>
      <nav className="mt-1 flex-1 overflow-y-auto px-2 scrollbar-thin">
        {threads.length === 0 && (
          <div className="px-2 py-3 text-xs text-fg-subtle">
            No conversations yet.
          </div>
        )}
        {threads.map((t) => {
          const active = t.id === activeId;
          return (
            <div
              key={t.id}
              className={`group mb-0.5 flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer ${
                active
                  ? "bg-bg-muted text-fg"
                  : "text-fg-muted hover:bg-bg-muted hover:text-fg"
              }`}
              onClick={() => onSelect(t.id)}
            >
              {editingId === t.id ? (
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={() => {
                    if (draft.trim() && draft !== t.title) onRename(t.id, draft.trim());
                    setEditingId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="flex-1 rounded bg-bg px-1.5 py-0.5 text-sm outline-none border border-accent"
                />
              ) : (
                <span className="flex-1 truncate">{t.title}</span>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setEditingId(t.id);
                  setDraft(t.title);
                }}
                className="opacity-0 group-hover:opacity-100 rounded p-1 hover:bg-bg text-fg-subtle"
                aria-label="Rename"
              >
                <MoreHorizontal size={14} />
              </button>
            </div>
          );
        })}
      </nav>

      {/* Footer actions */}
      <div className="border-t border-border px-2 py-2">
        <button
          onClick={onOpenCapabilities}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-fg-muted hover:bg-bg-muted hover:text-fg"
        >
          <Sparkles size={15} />
          What can I ask?
        </button>
        <button
          onClick={onOpenGlossary}
          className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-fg-muted hover:bg-bg-muted hover:text-fg"
        >
          <BookOpen size={15} />
          Business glossary
        </button>
        <div className="mt-2 flex items-center justify-between px-3 py-1.5 text-[11px] text-fg-subtle">
          <span className="truncate">
            {PILOT_USER.id} · {PILOT_USER.role}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
