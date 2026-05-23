"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

const CUSTOM_SPEC_PREFIX = "openai_compatible/embedding-";

function isLocalhostUrl(url: string): boolean {
  return /\b(localhost|127\.0\.0\.1)\b/.test(url);
}

type EmbeddingSpec = {
  id: string;
  provider: string;
  model_id: string;
  dimension: number;
  label: string;
  cost_per_1m_tokens: number | null;
  notes: string | null;
  api_key_configured: boolean;
};

type CatalogResp = {
  active_spec_id: string | null;
  specs: EmbeddingSpec[];
  custom_model_id?: string | null;
};

type StatusResp = {
  active_spec_id: string | null;
  total_pages: number;
  embedded_pages: number;
  current_job: JobResp | null;
};

type JobResp = {
  id: string;
  model_spec_id: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total_pages: number;
  done_pages: number;
  error_message: string | null;
};

type FetchedModel = { id: string; label: string };

export function EmbeddingSettingsCard() {
  const [catalog, setCatalog] = useState<CatalogResp | null>(null);
  const [status, setStatus] = useState<StatusResp | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // Masked keys per provider, e.g. {"google": "••••••••P258"}. Loaded from
  // /api/settings; the bullet character means "key already saved server-side".
  const [maskedKeys, setMaskedKeys] = useState<Record<string, string>>({});
  const [apiKey, setApiKey] = useState("");
  const [origBaseUrl, setOrigBaseUrl] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  // Custom OpenAI-compatible model name
  const [customModelId, setCustomModelId] = useState("");
  const [origCustomModelId, setOrigCustomModelId] = useState("");
  const [fetchedModels, setFetchedModels] = useState<FetchedModel[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchModelsError, setFetchModelsError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void refresh();
  }, []);

  // When the user picks a different model, prefill the input with that
  // provider's masked key (or empty if none).
  useEffect(() => {
    const provider = catalog?.specs.find((s) => s.id === selected)?.provider;
    setApiKey(provider ? maskedKeys[provider] ?? "" : "");
  }, [selected, maskedKeys, catalog]);

  // Poll active job every 2s while one is running.
  useEffect(() => {
    const job = status?.current_job;
    if (!job || (job.status !== "pending" && job.status !== "running")) return;
    const t = setInterval(() => {
      void refreshStatus();
    }, 2000);
    return () => clearInterval(t);
  }, [status?.current_job?.id, status?.current_job?.status]);

  async function refresh() {
    try {
      const [c, s, settings] = await Promise.all([
        api<CatalogResp>("/api/settings/embeddings/catalog"),
        api<StatusResp>("/api/settings/embeddings/status"),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      setStatus(s);
      const masked: Record<string, string> = {};
      for (const provider of new Set(c.specs.map((sp) => sp.provider))) {
        const v = settings[`embedding_api_key__${provider}`];
        if (typeof v === "string" && v.length > 0) masked[provider] = v;
      }
      setMaskedKeys(masked);

      const bVal = settings["embedding_base_url"];
      const bStr = typeof bVal === "string" ? bVal : "";
      setOrigBaseUrl(bStr);
      setBaseUrl(bStr);

      const cmid = c.custom_model_id ?? "";
      setOrigCustomModelId(cmid);
      setCustomModelId(cmid);

      if (!selected) setSelected(c.active_spec_id ?? c.specs[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load embedding catalog");
    }
  }

  async function refreshStatus() {
    try {
      const s = await api<StatusResp>("/api/settings/embeddings/status");
      setStatus(s);
    } catch {
      // ignore — keep last known
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  const isCustomSpec = !!selected && selected.startsWith(CUSTOM_SPEC_PREFIX);
  const job = status?.current_job ?? null;
  const jobBusy = job && (job.status === "pending" || job.status === "running");
  const isActiveSelected = selectedSpec?.id === catalog?.active_spec_id;
  const willSwitch = !!selectedSpec && !isActiveSelected;
  const isMaskedKey = apiKey.includes("•");
  const hasNewKey = apiKey.trim().length > 0 && !isMaskedKey;
  const hasNewBaseUrl = baseUrl.trim() !== origBaseUrl;
  const hasNewCustomModelId = isCustomSpec && customModelId.trim() !== origCustomModelId;

  const canSave = isCustomSpec
    ? !!customModelId.trim() && !jobBusy && (hasNewKey || hasNewBaseUrl || hasNewCustomModelId || willSwitch)
    : !!selectedSpec &&
      !jobBusy &&
      (hasNewKey || hasNewBaseUrl || (willSwitch && (selectedSpec.api_key_configured || hasNewKey)));

  // Retrieve the current provider's masked key for onBlur restore.
  const currentProviderMaskedKey = (() => {
    const provider = catalog?.specs.find((s) => s.id === selected)?.provider;
    return provider ? maskedKeys[provider] ?? "" : "";
  })();

  async function handleFetchModels() {
    if (!baseUrl.trim()) return;
    setFetchingModels(true);
    setFetchModelsError("");
    setFetchedModels([]);
    try {
      const modelsUrl = baseUrl.trim().replace(/\/+$/, "") + "/models";
      const headers: Record<string, string> = {};
      if (apiKey && !isMaskedKey && apiKey.trim()) {
        headers["Authorization"] = `Bearer ${apiKey.trim()}`;
      }
      const resp = await fetch(modelsUrl, { headers });
      if (!resp.ok) throw new Error(`Server returned HTTP ${resp.status}`);
      const data = (await resp.json()) as { data?: { id: string }[] } | { id: string }[];
      const list: FetchedModel[] = [];
      const items = Array.isArray(data) ? data : (data as { data?: { id: string }[] }).data ?? [];
      for (const m of items) {
        if (m?.id) list.push({ id: m.id, label: m.id });
      }
      setFetchedModels(list);
      if (list.length === 0) setFetchModelsError("No models found at this URL.");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to fetch";
      setFetchModelsError(
        `${msg}. Make sure LM Studio / Ollama is running and CORS is enabled.`
      );
    } finally {
      setFetchingModels(false);
    }
  }

  async function handleSave() {
    if (!selectedSpec) return;
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const settingsUpdates: Record<string, string> = {};
      if (hasNewKey) {
        settingsUpdates[`embedding_api_key__${selectedSpec.provider}`] = apiKey.trim();
      }
      if (hasNewBaseUrl) {
        settingsUpdates["embedding_base_url"] = baseUrl.trim();
      }

      if (Object.keys(settingsUpdates).length > 0) {
        await api("/api/settings", {
          method: "PUT",
          body: { settings: settingsUpdates },
        });
      }

      // Trigger switch if: different model selected, OR custom spec with new model name.
      if (willSwitch || (isCustomSpec && hasNewCustomModelId)) {
        const body: Record<string, string> = { model_spec_id: selectedSpec.id };
        if (isCustomSpec && customModelId.trim()) {
          body.custom_model_id = customModelId.trim();
        }
        await api("/api/settings/embeddings/switch", { method: "POST", body });
      }

      await refresh();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function cancelJob() {
    if (!job) return;
    try {
      await api(`/api/settings/embeddings/jobs/${job.id}/cancel`, {
        method: "POST",
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
    }
  }

  if (!catalog || !status) {
    return (
      <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
        <p className="text-sm text-muted-foreground">Loading embedding catalog…</p>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">data_array</span>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">Embedding Model</h3>
          <p className="text-xs text-muted-foreground">
            Choose a model and save its API key.
          </p>
        </div>
      </div>

      {/* Job progress */}
      {jobBusy && (
        <div className="mb-4 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span>
              Migrating to <strong>{job.model_spec_id}</strong> — {job.done_pages}/{job.total_pages} pages
            </span>
            <button onClick={cancelJob} className="text-xs underline hover:no-underline">
              Cancel
            </button>
          </div>
          <div className="h-2 rounded bg-blue-100 dark:bg-blue-900 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all"
              style={{
                width: `${
                  job.total_pages > 0 ? Math.round((job.done_pages / job.total_pages) * 100) : 0
                }%`,
              }}
            />
          </div>
        </div>
      )}

      {job?.status === "failed" && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-xs">
          <strong>Migration failed:</strong> {job.error_message || "unknown"}
        </div>
      )}

      {/* Model list */}
      <div className="flex flex-col gap-2 mb-4">
        {catalog.specs.map((spec) => {
          const isActive = spec.id === catalog.active_spec_id;
          const isChecked = spec.id === selected;
          const isCustomEntry = spec.id.startsWith(CUSTOM_SPEC_PREFIX);
          return (
            <label
              key={spec.id}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                isChecked ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"
              }`}
            >
              <input
                type="radio"
                name="embedding-spec"
                value={spec.id}
                checked={isChecked}
                onChange={() => {
                  setSelected(spec.id);
                  setFetchedModels([]);
                  setFetchModelsError("");
                }}
                disabled={!!jobBusy}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{spec.label}</span>
                  {isActive && (
                    <span className="text-[10px] uppercase tracking-wide bg-green-500/15 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                  {isActive && isCustomEntry && catalog.custom_model_id && (
                    <span className="text-[10px] font-mono bg-muted px-1.5 py-0.5 rounded text-muted-foreground">
                      {catalog.custom_model_id}
                    </span>
                  )}
                </div>
                {spec.notes && (
                  <p className="text-[11px] text-muted-foreground/80 mt-1 italic">{spec.notes}</p>
                )}
              </div>
            </label>
          );
        })}
      </div>

      {/* API key + Custom Base URL — grouped together */}
      {selectedSpec && (
        <div className="flex flex-col gap-4 mb-4">
          {/* Base URL */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs flex items-center justify-between">
              <span>{isCustomSpec ? "Server URL (Base URL)" : "Custom API URL (Base URL)"}</span>
              {!isCustomSpec && (
                <span className="text-[10px] text-muted-foreground font-normal">Optional</span>
              )}
            </Label>
            <Input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={
                isCustomSpec
                  ? "http://host.docker.internal:1234/v1"
                  : "e.g. http://host.docker.internal:1234/v1"
              }
              className="bg-background font-mono text-xs"
            />
            {isCustomSpec && isLocalhostUrl(baseUrl) && (
              <div className="flex items-start gap-1.5 p-2 rounded-lg bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800">
                <span className="material-symbols-outlined text-amber-600 dark:text-amber-400 text-sm shrink-0 mt-px">warning</span>
                <div className="text-[11px] text-amber-800 dark:text-amber-300 leading-normal">
                  <strong>Running in Docker?</strong> Replace{" "}
                  <code className="bg-amber-100 dark:bg-amber-900/50 px-1 rounded font-mono text-[10px]">localhost</code>{" "}
                  with{" "}
                  <button
                    type="button"
                    onClick={() => setBaseUrl(baseUrl.replace(/127\.0\.0\.1|localhost/g, "host.docker.internal"))}
                    className="font-mono text-[10px] bg-amber-100 dark:bg-amber-900/50 px-1 rounded underline hover:no-underline cursor-pointer"
                  >
                    host.docker.internal
                  </button>{" "}
                  so the backend worker can reach the server.
                </div>
              </div>
            )}
            {!isCustomSpec && (
              <p className="text-[10px] text-muted-foreground/80 leading-normal">
                For local integration like LM Studio, enter <code className="bg-muted px-1 py-0.5 rounded text-[9px] font-mono">http://host.docker.internal:1234/v1</code>.
              </p>
            )}
          </div>

          {/* API key */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">
              API key for {selectedSpec.provider}
              {isCustomSpec && (
                <span className="ml-1 text-muted-foreground font-normal">(optional for LM Studio)</span>
              )}
              {selectedSpec.api_key_configured && (
                <span className="ml-2 text-green-600 dark:text-green-400">✓ saved</span>
              )}
            </Label>
            <Input
              type={isMaskedKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onFocus={() => {
                if (isMaskedKey) setApiKey("");
              }}
              onBlur={() => {
                if (!apiKey) setApiKey(currentProviderMaskedKey);
              }}
              placeholder={
                isCustomSpec
                  ? "lm-studio  (any string works, or leave empty)"
                  : selectedSpec.api_key_configured
                  ? "Replace existing key…"
                  : "Paste API key"
              }
              className="bg-background"
            />
          </div>

          {/* Model name — only for custom OpenAI-compatible specs */}
          {isCustomSpec && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">
                Model name
                <span className="ml-1 text-destructive">*</span>
              </Label>
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={customModelId}
                  onChange={(e) => setCustomModelId(e.target.value)}
                  placeholder="e.g. nomic-ai/nomic-embed-text-v1.5"
                  className="bg-background font-mono text-xs flex-1"
                />
                <button
                  type="button"
                  disabled={!baseUrl.trim() || fetchingModels}
                  onClick={handleFetchModels}
                  className="shrink-0 px-3 py-2 rounded-lg border border-border text-xs hover:bg-accent/50 disabled:opacity-50 transition-colors"
                  title="Fetch available models from server"
                >
                  {fetchingModels ? (
                    <span className="material-symbols-outlined text-sm animate-spin">
                      progress_activity
                    </span>
                  ) : (
                    <span className="material-symbols-outlined text-sm">refresh</span>
                  )}
                </button>
              </div>
              {fetchModelsError && (
                <p className="text-[11px] text-destructive">{fetchModelsError}</p>
              )}
              {fetchedModels.length > 0 && (
                <div className="flex flex-col gap-1 max-h-40 overflow-y-auto rounded-lg border border-border">
                  {fetchedModels.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        setCustomModelId(m.id);
                        setFetchedModels([]);
                      }}
                      className={`text-left px-3 py-2 text-xs font-mono hover:bg-accent/40 transition-colors ${
                        customModelId === m.id ? "bg-primary/10 text-primary" : ""
                      }`}
                    >
                      {m.id}
                    </button>
                  ))}
                </div>
              )}
              <p className="text-[10px] text-muted-foreground/80">
                Enter the model name exactly, or click the refresh button to fetch available models from the server.
                Make sure the dimension above matches your model&apos;s output size.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Single Save button */}
      <div className="flex items-center gap-3">
        <button
          disabled={!canSave || saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {saving
            ? "Saving…"
            : willSwitch || (isCustomSpec && hasNewCustomModelId)
            ? "Switch & Re-embed"
            : "Save"}
        </button>
        {saved && (
          <span className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">check_circle</span>
            Saved
          </span>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}
