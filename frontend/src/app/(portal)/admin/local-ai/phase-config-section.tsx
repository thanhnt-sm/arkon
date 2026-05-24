"use client";

/**
 * PhaseConfigSection — reusable config card for vision / main_llm / embedding.
 *
 * Renders model_id, fallback_model_id, estimated_ram_gb, and context_length
 * fields. Advanced fields (eval_batch_size, gpu_ratio, flash_attention,
 * kv_cache_offload) are shown in a collapsible "Advanced" block.
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type VisionPhaseConfig = {
  model_id: string;
  fallback_model_id: string;
  estimated_ram_gb: number;
  context_length: number;
  eval_batch_size: number;
  gpu_ratio: number;
};

export type MainLLMPhaseConfig = {
  model_id: string;
  fallback_model_id: string;
  estimated_ram_gb: number;
  context_length: number;
  eval_batch_size: number;
  gpu_ratio: number;
  flash_attention: boolean;
  kv_cache_offload: boolean;
};

export type EmbeddingPhaseConfig = {
  model_id: string;
  fallback_model_id: string;
  estimated_ram_gb: number;
};

export type PhaseKey = "vision" | "main_llm" | "embedding";

// Union that covers all three — callers supply the narrower type
export type AnyPhaseConfig = VisionPhaseConfig | MainLLMPhaseConfig | EmbeddingPhaseConfig;

type PhaseConfigSectionProps = {
  title: string;
  phaseKey: PhaseKey;
  config: AnyPhaseConfig;
  onChange: (phaseKey: PhaseKey, field: string, value: string | number | boolean) => void;
  showAdvanced: boolean; // controlled by parent (true when mode=max)
  disabled?: boolean;
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FieldRow({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={cn(
        "h-9 w-full rounded-md border bg-background px-3 text-sm",
        "focus:outline-none focus:ring-1 focus:ring-foreground/20",
        disabled && "opacity-60 cursor-not-allowed",
      )}
    />
  );
}

function NumberInput({
  value,
  onChange,
  step,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <input
      type="number"
      value={value}
      step={step ?? 1}
      onChange={(e) => {
        const n = parseFloat(e.target.value);
        if (!Number.isNaN(n)) onChange(n);
      }}
      disabled={disabled}
      className={cn(
        "h-9 w-full rounded-md border bg-background px-3 text-sm",
        "focus:outline-none focus:ring-1 focus:ring-foreground/20",
        disabled && "opacity-60 cursor-not-allowed",
      )}
    />
  );
}

function CheckboxField({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="accent-foreground"
      />
      <span className="text-sm text-muted-foreground">{label}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PhaseConfigSection({
  title,
  phaseKey,
  config,
  onChange,
  showAdvanced,
  disabled = false,
}: PhaseConfigSectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const isEmbedding = phaseKey === "embedding";
  const isMainLLM = phaseKey === "main_llm";
  const isVision = phaseKey === "vision";

  // Type assertions — safe because phaseKey determines which fields exist
  const visionOrMain = config as VisionPhaseConfig;
  const mainLLM = config as MainLLMPhaseConfig;

  function set(field: string, value: string | number | boolean) {
    onChange(phaseKey, field, value);
  }

  return (
    <div className="rounded-xl border bg-card p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="text-sm font-semibold text-foreground">{title}</div>

      {/* Core fields — always visible */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <FieldRow label="Model ID" hint="HuggingFace repo path (org/model-name)">
          <TextInput
            value={config.model_id}
            onChange={(v) => set("model_id", v)}
            placeholder="org/model-name"
            disabled={disabled}
          />
        </FieldRow>

        <FieldRow label="Fallback Model ID" hint="Used when primary model fails to load">
          <TextInput
            value={config.fallback_model_id}
            onChange={(v) => set("fallback_model_id", v)}
            placeholder="org/fallback-model"
            disabled={disabled}
          />
        </FieldRow>

        <FieldRow label="Estimated RAM (GB)" hint="For RAM pre-flight check">
          <NumberInput
            value={config.estimated_ram_gb}
            onChange={(v) => set("estimated_ram_gb", v)}
            step={0.5}
            disabled={disabled}
          />
        </FieldRow>

        {!isEmbedding && (
          <FieldRow label="Context Length (tokens)">
            <NumberInput
              value={visionOrMain.context_length}
              onChange={(v) => set("context_length", v)}
              disabled={disabled}
            />
          </FieldRow>
        )}
      </div>

      {/* Advanced — collapsible, shown only when showAdvanced=true (mode=max) */}
      {showAdvanced && !isEmbedding && (
        <div className="border-t pt-3 flex flex-col gap-2">
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="flex items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground transition-colors w-fit"
          >
            <span
              className="material-symbols-outlined text-[14px]"
              style={{
                fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 14",
                transform: advancedOpen ? "rotate(0deg)" : "rotate(-90deg)",
                display: "inline-block",
                transition: "transform 150ms",
              }}
            >
              expand_more
            </span>
            Advanced (auto-applied in MAX mode)
          </button>

          {advancedOpen && (
            <div className="flex flex-col gap-3 pt-1">
              <div className="text-[11px] text-muted-foreground/70 bg-amber-50/60 border border-amber-200/60 rounded-md px-3 py-2">
                Sampling profiles are read-only in this iteration — configurable in next release.
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FieldRow label="Eval Batch Size">
                  <NumberInput
                    value={visionOrMain.eval_batch_size}
                    onChange={(v) => set("eval_batch_size", v)}
                    disabled={disabled}
                  />
                </FieldRow>

                <FieldRow label="GPU Ratio (0.0 – 1.0)" hint="Fraction of model layers on GPU">
                  <NumberInput
                    value={visionOrMain.gpu_ratio}
                    onChange={(v) => set("gpu_ratio", v)}
                    step={0.05}
                    disabled={disabled}
                  />
                </FieldRow>
              </div>

              {isMainLLM && (
                <div className="flex flex-col gap-2">
                  <CheckboxField
                    label="Flash Attention"
                    checked={mainLLM.flash_attention}
                    onChange={(v) => set("flash_attention", v)}
                    disabled={disabled}
                  />
                  <CheckboxField
                    label="KV Cache Offload"
                    checked={mainLLM.kv_cache_offload}
                    onChange={(v) => set("kv_cache_offload", v)}
                    disabled={disabled}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
