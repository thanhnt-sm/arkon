"use client";

/**
 * /admin/local-ai — Local AI Orchestrator configuration page.
 *
 * Allows admins to configure mode (off/max/other), per-phase model IDs,
 * LM Studio connection, and trigger preset resets + connection tests.
 */

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { ModeSelector, type LocalAIMode } from "./mode-selector";
import {
  PhaseConfigSection,
  type AnyPhaseConfig,
  type EmbeddingPhaseConfig,
  type MainLLMPhaseConfig,
  type PhaseKey,
  type VisionPhaseConfig,
} from "./phase-config-section";

// ---------------------------------------------------------------------------
// Types mirroring LocalAIConfigOut from the backend
// ---------------------------------------------------------------------------

type SamplingProfileData = {
  temperature: number;
  top_p: number;
  top_k: number | null;
  min_p: number | null;
  repeat_penalty: number | null;
};

type SettingsModelData = {
  llm_model_id?: string | null;
  vision_model_id?: string | null;
  embedding_model_id?: string | null;
  lms_host?: string | null;
};

type LocalAIConfigData = {
  mode: LocalAIMode;
  lms_host: string;
  lms_auth_token: string;
  ram_headroom_gb: number;
  vision: VisionPhaseConfig;
  main_llm: MainLLMPhaseConfig;
  embedding: EmbeddingPhaseConfig;
  sampling: {
    refine: SamplingProfileData;
    map: SamplingProfileData;
    verify: SamplingProfileData;
    reduce: SamplingProfileData;
    digest: SamplingProfileData;
    vision: SamplingProfileData;
  };
  settings_models?: SettingsModelData;
};

type LocalAIConfigSaveBody = {
  mode: LocalAIMode;
  lms_host: string;
  lms_auth_token?: string;
  ram_headroom_gb: number;
  vision: VisionPhaseConfig;
  main_llm: MainLLMPhaseConfig;
  embedding: EmbeddingPhaseConfig;
};

type HealthResult = {
  ok: boolean;
  message: string;
  loaded_models: string[];
};

type StatusChip = {
  kind: "success" | "error" | "info";
  message: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatusBanner({ chip }: { chip: StatusChip }) {
  const cls =
    chip.kind === "success"
      ? "bg-emerald-50 border-emerald-200 text-emerald-800"
      : chip.kind === "error"
      ? "bg-red-50 border-red-200 text-red-800"
      : "bg-blue-50 border-blue-200 text-blue-800";
  const icon =
    chip.kind === "success" ? "check_circle" : chip.kind === "error" ? "error" : "info";
  return (
    <div className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm ${cls}`}>
      <span
        className="material-symbols-outlined text-base shrink-0"
        style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
      >
        {icon}
      </span>
      {chip.message}
    </div>
  );
}

function FieldRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
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

const PHASE_LABELS: Record<PhaseKey, string> = {
  vision: "Vision phase",
  main_llm: "Main LLM phase",
  embedding: "Embedding phase",
};

type ModelPhaseConfig = AnyPhaseConfig & {
  model_id: string;
  fallback_model_id: string;
  estimated_ram_gb: number;
};

function normalizeModelPhase<T extends ModelPhaseConfig>(phase: T): T {
  return {
    ...phase,
    model_id: phase.model_id.trim(),
    fallback_model_id: phase.fallback_model_id.trim(),
  };
}

function getSaveValidationError(config: LocalAIConfigData): string | null {
  if (!config.lms_host.trim()) {
    return "Host URL cannot be blank.";
  }
  if (!Number.isFinite(config.ram_headroom_gb) || config.ram_headroom_gb < 0) {
    return "RAM headroom must be 0 or greater.";
  }

  const phases: Array<[PhaseKey, ModelPhaseConfig]> = [
    ["vision", config.vision],
    ["main_llm", config.main_llm],
    ["embedding", config.embedding],
  ];

  for (const [phaseKey, phase] of phases) {
    const label = PHASE_LABELS[phaseKey];
    if (!phase.model_id.trim()) return `${label} model ID cannot be blank.`;
    if (!phase.fallback_model_id.trim()) return `${label} fallback model ID cannot be blank.`;
    if (!Number.isFinite(phase.estimated_ram_gb) || phase.estimated_ram_gb <= 0) {
      return `${label} estimated RAM must be greater than 0.`;
    }
  }

  const runtimePhases: Array<[PhaseKey, VisionPhaseConfig | MainLLMPhaseConfig]> = [
    ["vision", config.vision],
    ["main_llm", config.main_llm],
  ];

  for (const [phaseKey, phase] of runtimePhases) {
    const label = PHASE_LABELS[phaseKey];
    if (!Number.isFinite(phase.context_length) || phase.context_length <= 0) {
      return `${label} context length must be greater than 0.`;
    }
    if (!Number.isFinite(phase.eval_batch_size) || phase.eval_batch_size <= 0) {
      return `${label} eval batch size must be greater than 0.`;
    }
    if (!Number.isFinite(phase.gpu_ratio) || phase.gpu_ratio < 0 || phase.gpu_ratio > 1) {
      return `${label} GPU ratio must be between 0 and 1.`;
    }
  }

  return null;
}

function buildSaveBody(config: LocalAIConfigData, tokenToSend: string | undefined): LocalAIConfigSaveBody {
  return {
    mode: config.mode,
    lms_host: config.lms_host.trim(),
    ...(tokenToSend !== undefined ? { lms_auth_token: tokenToSend } : {}),
    ram_headroom_gb: config.ram_headroom_gb,
    vision: normalizeModelPhase(config.vision),
    main_llm: normalizeModelPhase(config.main_llm),
    embedding: normalizeModelPhase(config.embedding),
  };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LocalAIAdminPage() {
  const router = useRouter();
  const { user } = useAuth();

  const [config, setConfig] = useState<LocalAIConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [statusChip, setStatusChip] = useState<StatusChip | null>(null);
  const [healthResult, setHealthResult] = useState<HealthResult | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

  // Redirect non-admins
  useEffect(() => {
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, router]);

  useEffect(() => {
    if (user?.role !== "admin") return;

    let cancelled = false;
    api<LocalAIConfigData>("/api/admin/local-ai/config")
      .then((data) => {
        if (!cancelled) setConfig(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setStatusChip({
          kind: "error",
          message: e instanceof Error ? e.message : "Failed to load config",
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user?.role]);

  // ── Mutations ──────────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!config) return;
    const validationError = getSaveValidationError(config);
    if (validationError) {
      setStatusChip({ kind: "error", message: validationError });
      return;
    }

    setSaving(true);
    setStatusChip(null);
    try {
      // auth_token: if it's the masked placeholder or empty, omit so backend keeps existing
      const tokenToSend =
        config.lms_auth_token === "•••" || config.lms_auth_token === ""
          ? undefined
          : config.lms_auth_token;

      const updated = await api<LocalAIConfigData>("/api/admin/local-ai/config", {
        method: "POST",
        body: buildSaveBody(config, tokenToSend),
      });
      setConfig(updated);
      setStatusChip({ kind: "success", message: "Configuration saved. New jobs use it on their next Local AI call." });
    } catch (e) {
      setStatusChip({
        kind: "error",
        message: e instanceof Error ? e.message : "Save failed",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setHealthResult(null);
    setStatusChip(null);
    try {
      const result = await api<HealthResult>("/api/admin/local-ai/health");
      setHealthResult(result);
      setStatusChip({
        kind: result.ok ? "success" : "error",
        message: result.ok
          ? `LM Studio reachable. Loaded: ${result.loaded_models.length > 0 ? result.loaded_models.join(", ") : "none"}`
          : `LM Studio unreachable — ${result.message}`,
      });
    } catch (e) {
      setStatusChip({
        kind: "error",
        message: e instanceof Error ? e.message : "Connection test failed",
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSyncSettings = async () => {
    setSyncing(true);
    setStatusChip(null);
    try {
      const updated = await api<LocalAIConfigData>("/api/admin/local-ai/sync-settings", {
        method: "POST",
      });
      setConfig(updated);
      setStatusChip({ kind: "success", message: "Local AI now uses the models selected in Settings." });
    } catch (e) {
      setStatusChip({
        kind: "error",
        message: e instanceof Error ? e.message : "Sync from Settings failed",
      });
    } finally {
      setSyncing(false);
    }
  };

  const handleResetConfirmed = async () => {
    setShowResetConfirm(false);
    setResetting(true);
    setStatusChip(null);
    try {
      const updated = await api<LocalAIConfigData>("/api/admin/local-ai/reset-max", {
        method: "POST",
      });
      setConfig(updated);
      setStatusChip({ kind: "success", message: "Reset to MAX preset complete." });
    } catch (e) {
      setStatusChip({
        kind: "error",
        message: e instanceof Error ? e.message : "Reset failed",
      });
    } finally {
      setResetting(false);
    }
  };

  // ── Config mutations ───────────────────────────────────────────────────

  const setMode = (mode: LocalAIMode) => {
    setConfig((prev) => (prev ? { ...prev, mode } : prev));
  };

  const setTopField = (field: "lms_host" | "lms_auth_token" | "ram_headroom_gb", value: string | number) => {
    setConfig((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  const handlePhaseChange = (phaseKey: PhaseKey, field: string, value: string | number | boolean) => {
    setConfig((prev) => {
      if (!prev) return prev;
      const phase = prev[phaseKey] as Record<string, unknown>;
      return { ...prev, [phaseKey]: { ...phase, [field]: value } };
    });
  };

  // ── Guard ──────────────────────────────────────────────────────────────

  if (!user || user.role !== "admin") {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────

  const showAdvanced = config?.mode === "max";
  const busy = saving || resetting || syncing;
  const settingsModels = config?.settings_models;
  const settingsDiffers = Boolean(
    config &&
      settingsModels &&
      ((settingsModels.lms_host && settingsModels.lms_host !== config.lms_host) ||
        (settingsModels.llm_model_id && settingsModels.llm_model_id !== config.main_llm.model_id) ||
        (settingsModels.vision_model_id && settingsModels.vision_model_id !== config.vision.model_id) ||
        (settingsModels.embedding_model_id && settingsModels.embedding_model_id !== config.embedding.model_id)),
  );

  return (
    <>
      <PageHeader
        title="Local AI Orchestrator"
        description="Configure the on-device LM Studio stack. Mode selects the preset; individual fields override specific values."
        action={
          <div className="flex gap-2 flex-wrap">
            <Button
              variant="outline"
              onClick={handleTestConnection}
              disabled={loading || testing || !config}
            >
              <span
                className={`material-symbols-outlined text-base mr-2 ${testing ? "animate-spin" : ""}`}
                style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
              >
                {testing ? "progress_activity" : "health_and_safety"}
              </span>
              {testing ? "Testing…" : "Test Connection"}
            </Button>

            <Button
              variant={settingsDiffers ? "default" : "outline"}
              onClick={handleSyncSettings}
              disabled={busy || loading || !config}
            >
              <span
                className={`material-symbols-outlined text-base mr-2 ${syncing ? "animate-spin" : ""}`}
                style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
              >
                {syncing ? "progress_activity" : "sync_alt"}
              </span>
              {syncing ? "Applying…" : "Use Settings Models"}
            </Button>

            <Button
              variant="outline"
              onClick={() => setShowResetConfirm(true)}
              disabled={busy || loading || !config}
            >
              <span
                className="material-symbols-outlined text-base mr-2"
                style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
              >
                restart_alt
              </span>
              Reset to MAX
            </Button>

            <Button onClick={handleSave} disabled={busy || loading || !config}>
              <span
                className={`material-symbols-outlined text-base mr-2 ${saving ? "animate-spin" : ""}`}
                style={{ fontVariationSettings: "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
              >
                {saving ? "progress_activity" : "save"}
              </span>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        }
      />

      {/* Status banner */}
      {statusChip && (
        <div className="mt-4">
          <StatusBanner chip={statusChip} />
        </div>
      )}

      {/* Reset confirm inline */}
      {showResetConfirm && (
        <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 flex items-center gap-3 text-sm">
          <span
            className="material-symbols-outlined text-amber-600 shrink-0"
            style={{ fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
          >
            warning
          </span>
          <span className="flex-1 text-amber-900">
            This will overwrite all model IDs and tuning fields with the MAX preset defaults.
            LM Studio connection settings will be preserved.
          </span>
          <div className="flex gap-2">
            <button
              className="text-amber-700 hover:text-amber-900 underline text-xs"
              onClick={() => setShowResetConfirm(false)}
            >
              Cancel
            </button>
            <button
              className="text-red-700 hover:text-red-900 underline text-xs font-semibold"
              onClick={handleResetConfirmed}
            >
              Confirm Reset
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="mt-8 flex justify-center">
          <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
            progress_activity
          </span>
        </div>
      ) : config ? (
        <div className="mt-6 flex flex-col gap-6">
          {/* Mode selector */}
          <section>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              Mode
            </div>
            <ModeSelector value={config.mode} onChange={setMode} disabled={busy} />
            {settingsDiffers && (
              <p className="mt-2 text-xs text-amber-700">
                Settings currently points to different model IDs. Use Settings Models to copy them here.
              </p>
            )}
          </section>

          {/* LM Studio connection */}
          <section className="rounded-xl border bg-card p-4 flex flex-col gap-4">
            <div className="text-sm font-semibold">LM Studio Connection</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FieldRow label="Host URL" hint="e.g. http://host.docker.internal:1234">
                <input
                  type="text"
                  value={config.lms_host}
                  onChange={(e) => setTopField("lms_host", e.target.value)}
                  disabled={busy}
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground/20 disabled:opacity-60"
                />
              </FieldRow>
              <FieldRow
                label="Auth Token"
                hint="Write-only. Leave as-is to keep existing token."
              >
                <input
                  type="password"
                  value={config.lms_auth_token}
                  onChange={(e) => setTopField("lms_auth_token", e.target.value)}
                  disabled={busy}
                  placeholder="No token set"
                  autoComplete="new-password"
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground/20 disabled:opacity-60"
                />
              </FieldRow>
              <FieldRow label="RAM Headroom (GB)" hint="Free RAM reserved for OS and other processes">
                <input
                  type="number"
                  value={config.ram_headroom_gb}
                  step={0.5}
                  min={0}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!Number.isNaN(n)) setTopField("ram_headroom_gb", n);
                  }}
                  disabled={busy}
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground/20 disabled:opacity-60"
                />
              </FieldRow>
            </div>

            {/* Health result — loaded models */}
            {healthResult?.ok && healthResult.loaded_models.length > 0 && (
              <div className="text-[12px] text-muted-foreground">
                Loaded:{" "}
                {healthResult.loaded_models.map((m) => (
                  <span key={m} className="font-mono bg-muted rounded px-1 mr-1">{m}</span>
                ))}
              </div>
            )}

            {settingsModels && (
              <div className="rounded-md border bg-muted/30 px-3 py-2 text-[12px] text-muted-foreground">
                <div className="font-semibold text-foreground">Settings selection</div>
                <div className="mt-1 grid grid-cols-1 gap-1 font-mono">
                  {settingsModels.lms_host && <span>LMS: {settingsModels.lms_host}</span>}
                  {settingsModels.llm_model_id && <span>LLM: {settingsModels.llm_model_id}</span>}
                  {settingsModels.vision_model_id && <span>Vision: {settingsModels.vision_model_id}</span>}
                  {settingsModels.embedding_model_id && <span>Embedding: {settingsModels.embedding_model_id}</span>}
                </div>
              </div>
            )}
          </section>

          {/* Per-phase sections — only shown when mode != off */}
          {config.mode !== "off" && (
            <>
              <PhaseConfigSection
                title="Vision Phase"
                phaseKey="vision"
                config={config.vision as AnyPhaseConfig}
                onChange={handlePhaseChange}
                showAdvanced={showAdvanced ?? false}
                disabled={busy}
              />
              <PhaseConfigSection
                title="Main LLM Phase (Map / Reduce / Refine / Verify / Digest)"
                phaseKey="main_llm"
                config={config.main_llm as AnyPhaseConfig}
                onChange={handlePhaseChange}
                showAdvanced={showAdvanced ?? false}
                disabled={busy}
              />
              <PhaseConfigSection
                title="Embedding Phase"
                phaseKey="embedding"
                config={config.embedding as AnyPhaseConfig}
                onChange={handlePhaseChange}
                showAdvanced={false}
                disabled={busy}
              />
            </>
          )}

          {config.mode === "off" && (
            <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
              Local AI is disabled. Select Max or Other to configure model phases.
            </div>
          )}
        </div>
      ) : (
        <div className="mt-8 text-sm text-muted-foreground text-center">
          Failed to load configuration. Check console for details.
        </div>
      )}
    </>
  );
}
