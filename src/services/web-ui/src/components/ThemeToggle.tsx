"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/lib/theme";

export function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  const next = choice === "light" ? "dark" : choice === "dark" ? "system" : "light";
  const Icon = choice === "light" ? Sun : choice === "dark" ? Moon : Monitor;
  const label =
    choice === "light"
      ? "Light theme — switch to dark"
      : choice === "dark"
      ? "Dark theme — switch to system"
      : "System theme — switch to light";
  return (
    <button
      onClick={() => setChoice(next)}
      className="rounded p-1.5 text-fg-muted hover:bg-bg-muted hover:text-fg"
      aria-label={label}
      title={label}
    >
      <Icon size={14} />
    </button>
  );
}
