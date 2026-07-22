"use client";

import { PILOT_USER } from "@/lib/config";

interface Props {
  content: string;
}

export function UserBubble({ content }: Props) {
  return (
    <div className="flex gap-3 justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent text-accent-fg px-4 py-2.5 text-[15px] leading-7 whitespace-pre-wrap">
        {content}
      </div>
      <div
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bg-muted text-[11px] font-semibold text-fg-muted"
        title={`${PILOT_USER.id} · ${PILOT_USER.role}`}
      >
        {PILOT_USER.id.slice(0, 2).toUpperCase()}
      </div>
    </div>
  );
}
