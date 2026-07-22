"use client";

interface Props {
  title: string;
}

export function Header({ title }: Props) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-bg px-5">
      <h1 className="truncate text-[14px] font-medium text-fg">{title}</h1>
      <div className="text-[11px] text-fg-subtle">
        Read-only · Governed · Audited
      </div>
    </header>
  );
}
