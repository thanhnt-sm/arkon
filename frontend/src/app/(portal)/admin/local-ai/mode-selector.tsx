"use client";

/** Mode selector — pure presentational radio group for Off / Max / Other. */

import React from "react";
import { cn } from "@/lib/utils";

export type LocalAIMode = "off" | "max" | "other";

type ModeOption = {
  value: LocalAIMode;
  label: string;
  description: string;
};

const MODE_OPTIONS: ModeOption[] = [
  {
    value: "off",
    label: "Off",
    description: "Local AI disabled. Cloud providers are used for all phases.",
  },
  {
    value: "max",
    label: "Max",
    description:
      "Full local stack with researched M1 Max defaults (vision + main LLM + embedding). Auto-applies tuned sampling profiles.",
  },
  {
    value: "other",
    label: "Other",
    description:
      "Custom model selection. Advanced sampling profiles are not auto-applied; configure them manually.",
  },
];

type ModeSelectorProps = {
  value: LocalAIMode;
  onChange: (mode: LocalAIMode) => void;
  disabled?: boolean;
};

export function ModeSelector({ value, onChange, disabled = false }: ModeSelectorProps) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:gap-3">
      {MODE_OPTIONS.map((opt) => {
        const active = value === opt.value;
        return (
          <label
            key={opt.value}
            className={cn(
              "flex flex-1 cursor-pointer flex-col gap-1 rounded-xl border p-3 transition-colors",
              active
                ? "border-foreground/30 bg-black/[0.03]"
                : "border-border bg-card hover:bg-black/[0.02]",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <div className="flex items-center gap-2">
              <input
                type="radio"
                name="local-ai-mode"
                value={opt.value}
                checked={active}
                disabled={disabled}
                onChange={() => onChange(opt.value)}
                className="accent-foreground"
              />
              <span className={cn("text-sm font-semibold", active ? "text-foreground" : "text-muted-foreground")}>
                {opt.label}
              </span>
            </div>
            <p className="ml-[22px] text-[12px] text-muted-foreground leading-snug">
              {opt.description}
            </p>
          </label>
        );
      })}
    </div>
  );
}
