"use client";

import { ArrowRight, BookOpen, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { getExamples } from "@/lib/api";
import type { ExampleItem } from "@/lib/types";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/config";

interface Props {
  onPick: (q: string) => void;
  onOpenGlossary: () => void;
}

export function EmptyState({ onPick, onOpenGlossary }: Props) {
  const [examples, setExamples] = useState<ExampleItem[]>([]);

  useEffect(() => {
    getExamples()
      .then(setExamples)
      .catch(() => setExamples([]));
  }, []);

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-stretch px-5 py-12">
      <div className="mb-8">
        <div className="flex items-center gap-2 text-fg-muted text-sm">
          <Sparkles size={15} className="text-accent" />
          {PRODUCT_NAME}
        </div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">
          What would you like to know?
        </h2>
        <p className="mt-1 text-sm text-fg-muted">{PRODUCT_TAGLINE}</p>
      </div>

      {/* Curated golden examples */}
      <div className="mb-3 text-[11px] uppercase tracking-wider text-fg-subtle">
        Try one of these
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {examples.map((ex, i) => (
          <button
            key={i}
            onClick={() => onPick(ex.question)}
            className="group flex flex-col items-start gap-1 rounded-xl border border-border bg-bg-subtle px-4 py-3 text-left transition hover:border-accent/40 hover:bg-bg-muted"
          >
            <span className="text-[11px] uppercase tracking-wider text-fg-subtle">
              {ex.category}
            </span>
            <span className="flex w-full items-start justify-between gap-2 text-sm text-fg">
              <span className="flex-1">{ex.question}</span>
              <ArrowRight
                size={14}
                className="mt-0.5 shrink-0 text-fg-subtle transition group-hover:text-accent group-hover:translate-x-0.5"
              />
            </span>
          </button>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between rounded-xl border border-dashed border-border px-4 py-3 text-sm text-fg-muted">
        <div className="flex items-center gap-2">
          <BookOpen size={15} />
          New here? Browse the business glossary to see what terms I understand.
        </div>
        <button
          onClick={onOpenGlossary}
          className="rounded-md border border-border bg-bg px-3 py-1 text-xs font-medium hover:bg-bg-muted"
        >
          Open glossary
        </button>
      </div>
    </div>
  );
}
