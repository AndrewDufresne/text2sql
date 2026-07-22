"use client";

import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || disabled) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="border-t border-border bg-bg p-4">
      <div className="mx-auto max-w-3xl">
        <div
          className={`flex items-end gap-2 rounded-xl border border-border bg-bg-subtle px-3 py-2 transition focus-within:border-accent ${
            disabled ? "opacity-70" : ""
          }`}
        >
          <textarea
            ref={ref}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={
              disabled
                ? "Generating answer…"
                : "Ask about clients, exposures, transactions… (Enter to send, Shift+Enter for newline)"
            }
            disabled={disabled}
            className="flex-1 resize-none bg-transparent px-1 py-1.5 text-[15px] leading-6 text-fg placeholder:text-fg-subtle outline-none disabled:cursor-not-allowed"
          />
          <button
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg transition hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Send"
          >
            <ArrowUp size={16} />
          </button>
        </div>
        <div className="mt-2 px-1 text-[11px] text-fg-subtle">
          The assistant only reads from approved CIB tables and masks PII before
          display. SQL is executed read-only via Trino.
        </div>
      </div>
    </div>
  );
}
