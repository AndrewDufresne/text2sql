"use client";

import { Check, Database, Shield, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { getCapabilities } from "@/lib/api";
import type { Capabilities } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CapabilityDrawer({ open, onClose }: Props) {
  const [caps, setCaps] = useState<Capabilities | null>(null);

  useEffect(() => {
    if (!open) return;
    getCapabilities()
      .then(setCaps)
      .catch(() => setCaps(null));
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <aside className="absolute right-0 top-0 flex h-full w-[480px] max-w-full flex-col border-l border-border bg-bg shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <div className="text-sm font-semibold">What can I ask?</div>
            <div className="text-[11px] text-fg-subtle">
              Capability surface · {caps?.version || "—"}
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
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-3 space-y-5">
          {!caps && <div className="text-sm text-fg-muted">Loading…</div>}
          {caps && (
            <>
              <Section title="I can answer questions about" icon={<Check size={14} className="text-success" />}>
                <ul className="space-y-1">
                  {caps.can.map((s, i) => (
                    <li key={i} className="text-[13px] leading-6 text-fg-muted">
                      • {s}
                    </li>
                  ))}
                </ul>
              </Section>

              <Section title="I will refuse" icon={<XCircle size={14} className="text-danger" />}>
                <ul className="space-y-1">
                  {caps.cannot.map((s, i) => (
                    <li key={i} className="text-[13px] leading-6 text-fg-muted">
                      • {s}
                    </li>
                  ))}
                </ul>
              </Section>

              <Section title="Approved tables" icon={<Database size={14} className="text-fg-muted" />}>
                <div className="flex flex-wrap gap-1.5">
                  {caps.allowlisted_tables.map((t) => (
                    <span
                      key={t}
                      className="rounded-md border border-border bg-bg-subtle px-2 py-0.5 font-mono text-[11px] text-fg-muted"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </Section>

              <Section title="PII redaction" icon={<Shield size={14} className="text-warn" />}>
                <p className="text-[13px] leading-6 text-fg-muted">
                  These entity types are detected and masked before any value
                  appears in this UI:
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {caps.redacted_pii_entities.map((t) => (
                    <span
                      key={t}
                      className="rounded-md border border-border bg-bg-subtle px-2 py-0.5 font-mono text-[11px] text-fg-muted"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </Section>

              <Section title="Limits" icon={<Database size={14} className="text-fg-muted" />}>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
                  {Object.entries(caps.limits).flatMap(([k, v]) => [
                    <dt key={k + "-k"} className="text-fg-subtle">
                      {k.replace(/_/g, " ")}
                    </dt>,
                    <dd key={k + "-v"} className="font-mono text-fg">
                      {String(v)}
                    </dd>,
                  ])}
                </dl>
              </Section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-fg-subtle">
        {icon}
        {title}
      </div>
      {children}
    </section>
  );
}
