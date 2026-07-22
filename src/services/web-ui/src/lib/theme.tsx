"use client";

import { createContext, useContext, useEffect, useState } from "react";

type ThemeChoice = "light" | "dark" | "system";

interface ThemeCtx {
  choice: ThemeChoice;
  effective: "light" | "dark";
  setChoice: (c: ThemeChoice) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);
const STORAGE_KEY = "atlas.theme";

function resolveSystem(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>("system");
  const [effective, setEffective] = useState<"light" | "dark">("light");

  // Load + watch
  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) as ThemeChoice) || "system";
    setChoiceState(stored);
  }, []);

  useEffect(() => {
    const apply = () => {
      const next = choice === "system" ? resolveSystem() : choice;
      setEffective(next);
      const root = document.documentElement;
      if (next === "dark") root.classList.add("dark");
      else root.classList.remove("dark");
    };
    apply();
    if (choice === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [choice]);

  const setChoice = (c: ThemeChoice) => {
    localStorage.setItem(STORAGE_KEY, c);
    setChoiceState(c);
  };

  return (
    <Ctx.Provider value={{ choice, effective, setChoice }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme outside ThemeProvider");
  return ctx;
}
