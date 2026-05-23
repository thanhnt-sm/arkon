"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

const DEFAULT_CUSTOM_SPEC_ID = "openai_compatible/custom";

function isLocalhostUrl(url: string): boolean {
  return /\b(localhost|127\.0\.0\.1)\b/.test(url);
}

export type ModelSpec = {
  id: string;
  provider: string;
  model_id: string;
  label: string;
  notes: string | null;
  api_key_configured: boolean;
  // LLM-specific
  context_window_tokens?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  cost_per_1m_input_tokens?: number | null;
  cost_per_1m_output_tokens?: number | null;
  // Vision-specific
  max_image_size_mb?: number;
  cost_per_image?: number | null;
};

type CatalogResp = {
  active_spec_id: string | null;
  specs: ModelSpec[];
  custom_model_id?: string | null;
};

type FetchedModel = { id: string; label: string };

export function ModelCatalogCard({
  title,
  description,
  icon,
  catalogUrl,
  switchUrl,
  apiKeyConfigKey,
  customSpecId = DEFAULT_CUSTOM_SPEC_ID,
  renderMeta,
}: {
  title: string;
  description: string;
  icon: string;
  catalogUrl: string;
  switchUrl: string;
  apiKeyConfigKey: string;
  customSpecId?: string;
  renderMeta?: (spec: ModelSpec) => React.ReactNode;
}) {
  const [catalog, setCatalog] = useState<CatalogResp | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [maskedKey, setMaskedKey] = useState<string>("");
  const [apiKey, setApiKey] = useState<string>("");
  const [origBaseUrl, setOrigBaseUrl] = useState<string>("");
  const [baseUrl, setBaseUrl] = useState<string>("");
  // Custom OpenAI-compatible model name
  const [customModelId, setCustomModelId] = useState<string>("");
  const [origCustomModelId, setOrigCustomModelId] = useState<string>("");
  const [fetchedModels, setFetchedModels] = useState<FetchedModel[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [fetchModelsError, setFetchModelsError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const baseUrlConfigKey =
    apiKeyConfigKey === "llm_api_key" ? "llm_base_url" : "vision_base_url";

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    try {
      const [c, settings] = await Promise.all([
        api<CatalogResp>(catalogUrl),
        api<Record<string, unknown>>("/api/settings"),
      ]);
      setCatalog(c);
      const v = settings[apiKeyConfigKey];
      const masked = typeof v === "string" ? v : "";
      setMaskedKey(masked);
      setApiKey(masked);

      const bVal = settings[baseUrlConfigKey];
      const bStr = typeof bVal === "string" ? bVal : "";
      setOrigBaseUrl(bStr);
      setBaseUrl(bStr);

      // Custom model ID (from catalog response for LLM, not from settings)
      const cmid = c.custom_model_id ?? "";
      setOrigCustomModelId(cmid);
      setCustomModelId(cmid);

      setSelected((prev) => prev ?? c.active_spec_id ?? c.specs[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to load ${title}`);
    }
  }

  const selectedSpec = catalog?.specs.find((s) => s.id === selected) ?? null;
  const isCustomSpec = selected === customSpecId;
  const isActiveSelected = selectedSpec?.id === catalog?.active_spec_id;
  const willSwitch = !!selectedSpec && !isActiveSelected;
  const isMaskedKey = apiKey.includes("•");
  const hasNewKey = apiKey.trim().length > 0 && !isMaskedKey;
  const hasNewBaseUrl = baseUrl.trim() !== origBaseUrl;
  const hasNewCustomModelId = isCustomSpec && customModelId.trim() !== origCustomModelId;

  // For the custom spec: can save if there's a model name (key is optional for LM Studio)
  // For regular specs: need key or base URL change, or switching with key configured
  const canSave = isCustomSpec
    ? !!customModelId.trim() && (hasNewKey || hasNewBaseUrl || hasNewCustomModelId || willSwitch)
    : !!selectedSpec &&
      (hasNewKey ||
        hasNewBaseUrl ||
        (willSwitch && (selectedSpec.api_key_configured || hasNewKey)));

  // Fetch model list directly from the browser → LM Studio.
  // Must NOT go through the backend proxy because the backend runs inside Docker
  // where `localhost`/`127.0.0.1` resolves to the container, not the host.
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
        `${msg}. Make sure LM Studio is running and "Enable CORS" is turned on in its server settings.`
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
        settingsUpdates[apiKeyConfigKey] = apiKey.trim();
      }
      if (hasNewBaseUrl) {
        settingsUpdates[baseUrlConfigKey] = baseUrl.trim();
      }

      if (Object.keys(settingsUpdates).length > 0) {
        await api("/api/settings", {
          method: "PUT",
          body: { settings: settingsUpdates },
        });
      }

      // Call the switch endpoint when: (a) user is switching to a different model,
      // OR (b) custom spec is selected and the model name changed (to persist it).
      if (willSwitch || (isCustomSpec && hasNewCustomModelId)) {
        const body: Record<string, string> = { model_spec_id: selectedSpec.id };
        if (isCustomSpec && customModelId.trim()) {
          body.custom_model_id = customModelId.trim();
        }
        await api(switchUrl, { method: "POST", body });
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

  if (!catalog) {
    return (
      <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
        <p className="text-sm text-muted-foreground">Loading {title.toLowerCase()}…</p>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl p-6 border border-border shadow-sahara">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
          <span className="material-symbols-outlined text-primary text-base">{icon}</span>
        </div>
        <div className="flex-1">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>

      {/* Model list */}
      <div className="flex flex-col gap-2 mb-4">
        {catalog.specs.map((spec) => {
          const isActive = spec.id === catalog.active_spec_id;
          const isChecked = spec.id === selected;
          return (
            <label
              key={spec.id}
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                isChecked ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"
              }`}
            >
              <input
                type="radio"
                name={`${title}-spec`}
                value={spec.id}
                checked={isChecked}
                onChange={() => {
                  setSelected(spec.id);
                  setFetchedModels([]);
                  setFetchModelsError("");
                }}
                className="mt-1"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{spec.label}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground bg-secondary/40 px-1.5 py-0.5 rounded">
                    {spec.provider}
                  </span>
                  {isActive && (
                    <span className="text-[10px] uppercase tracking-wide bg-green-500/15 text-green-700 dark:text-green-400 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                  {isActive && spec.id === customSpecId && catalog.custom_model_id && (
                    <span className="text-[10px] font-mono bg-muted px-1.5 py-0.5 rounded text-muted-foreground">
                      {catalog.custom_model_id}
                    </span>
                  )}
                </div>
                {renderMeta && spec.id !== customSpecId && (
                  <div className="text-[11px] text-muted-foreground mt-1">
                    {renderMeta(spec)}
                  </div>
                )}
                {spec.notes && (
                  <p className="text-[11px] text-muted-foreground/80 mt-1 italic">{spec.notes}</p>
                )}
              </div>
            </label>
          );
        })}
      </div>

      {/* Per-spec config fields */}
      {selectedSpec && (
        <div className="flex flex-col gap-4 mb-4">
          {/* Base URL — always shown */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs flex items-center justify-between">
              <span>
                {isCustomSpec ? "Server URL (Base URL)" : "Custom API URL (Base URL)"}
              </span>
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
                  so the backend worker can reach LM Studio.
                  <span className="block mt-0.5 text-amber-700 dark:text-amber-400">
                    (Click the link above to auto-fix, or use localhost only if running Arkon without Docker.)
                  </span>
                </div>
              </div>
            )}
            {isCustomSpec && !isLocalhostUrl(baseUrl) && (
              <p className="text-[10px] text-muted-foreground/80">
                LM Studio default port: <code className="bg-muted px-1 py-0.5 rounded text-[9px] font-mono">1234</code>.
                The refresh button fetches models directly from your browser — LM Studio must have CORS enabled.
              </p>
            )}
          </div>

          {/* API Key */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">
              API key
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
                if (!apiKey) setApiKey(maskedKey);
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

          {/* Custom model name — for any custom OpenAI-compatible spec */}
          {isCustomSpec && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">
                Model name
                <span className="ml-1 text-destructive">*</span>
              </Label>
              {/* Fetch models button + dropdown */}
              <div className="flex gap-2">
                <Input
                  type="text"
                  value={customModelId}
                  onChange={(e) => setCustomModelId(e.target.value)}
                  placeholder="e.g. lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF"
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
                Enter the model name exactly as shown in LM Studio, or click the refresh button to fetch available models from the server.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          disabled={!canSave || saving}
          onClick={handleSave}
          className="bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? "Saving…" : willSwitch || (isCustomSpec && hasNewCustomModelId) ? "Switch & Save" : "Save"}
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
