"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL !== undefined
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://localhost:5055";

const SOURCES = [
  { id: "api", label: "API" },
  { id: "worker", label: "Workers" },
];

const LEVELS = ["ALL", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR"];

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-zinc-400",
  INFO: "text-sky-400",
  SUCCESS: "text-emerald-400",
  WARNING: "text-amber-400",
  ERROR: "text-rose-400",
  CRITICAL: "text-rose-600 font-bold",
};

function parseLine(raw: string) {
  // Format: 2025-05-23 10:30:45.123 | INFO     | name:fn:line | message
  const match = raw.match(
    /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) \| ([A-Z]+)\s*\| ([^|]+)\| (.*)$/
  );
  if (!match) return { raw, time: "", level: "", location: "", message: raw };
  return {
    raw,
    time: match[1],
    level: match[2].trim(),
    location: match[3].trim(),
    message: match[4],
  };
}

function LogLine({ raw, dimmed }: { raw: string; dimmed: boolean }) {
  const { time, level, location, message } = parseLine(raw);
  const color = LEVEL_COLORS[level] ?? "text-zinc-300";

  if (!time) {
    return (
      <div className={cn("font-mono text-xs leading-5 text-zinc-500", dimmed && "opacity-40")}>
        {raw}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "font-mono text-xs leading-5 flex gap-2 min-w-0",
        dimmed && "opacity-40"
      )}
    >
      <span className="text-zinc-600 shrink-0">{time}</span>
      <span className={cn("shrink-0 w-[60px]", color)}>{level}</span>
      <span className="text-zinc-600 shrink-0 hidden lg:block truncate max-w-[200px]">
        {location}
      </span>
      <span className="text-zinc-300 break-all">{message}</span>
    </div>
  );
}

export default function SystemLogsPage() {
  const [source, setSource] = useState("api");
  const [level, setLevel] = useState("ALL");
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [available, setAvailable] = useState(true);
  const [sourceStatus, setSourceStatus] = useState<Record<string, boolean>>({});

  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // Load snapshot
  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("arkon_token");
      const params = new URLSearchParams({ source, lines: "500" });
      if (level !== "ALL") params.set("level", level);
      const res = await fetch(`${API_BASE}/api/system/logs?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setLines(data.lines ?? []);
      setAvailable(data.available ?? false);
      setSourceStatus(data.sources ?? {});
    } catch {
      setLines([]);
      setAvailable(false);
    } finally {
      setLoading(false);
    }
  }, [source, level]);

  // Start/stop SSE stream
  const startStream = useCallback(() => {
    esRef.current?.close();
    const token = localStorage.getItem("arkon_token");
    const url = `${API_BASE}/api/system/logs/stream?source=${source}&token=${token}`;

    // SSE with auth via query param (EventSource doesn't support headers)
    // Backend must accept token from query if using SSE
    // Fallback: use fetch streaming
    setLines([]);

    const controller = new AbortController();
    const fetchStream = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/system/logs/stream?source=${source}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            try {
              const parsed = JSON.parse(dataLine.slice(6));
              if (parsed.line) {
                setLines((prev) => [...prev.slice(-2000), parsed.line]);
              }
            } catch {
              // skip malformed
            }
          }
        }
      } catch {
        // stream ended or aborted
      }
    };

    fetchStream();

    // Store abort controller to allow stopping
    (esRef as React.MutableRefObject<unknown>).current = { close: () => controller.abort() };
  }, [source]);

  const stopStream = useCallback(() => {
    if (esRef.current) {
      (esRef.current as { close: () => void }).close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (live) {
      startStream();
    } else {
      stopStream();
      loadSnapshot();
    }
    return () => stopStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, source]);

  useEffect(() => {
    if (!live) loadSnapshot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level]);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, autoScroll]);

  const handleDownload = () => {
    const token = localStorage.getItem("arkon_token");
    const a = document.createElement("a");
    a.href = `${API_BASE}/api/system/logs/download?source=${source}`;
    // Trigger with auth header via fetch + blob
    fetch(a.href, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        a.href = url;
        a.download = `arkon-${source}.log`;
        a.click();
        URL.revokeObjectURL(url);
      });
  };

  const filteredLines =
    level !== "ALL" && live
      ? lines.filter((l) => {
          const tag = `| ${level.padEnd(8)} |`;
          return l.includes(tag);
        })
      : lines;

  return (
    <>
      <PageHeader
        title="System Logs"
        description="Real-time and historical logs from API and worker processes."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              disabled={!available}
            >
              <span className="material-symbols-outlined text-base mr-1.5">download</span>
              Download
            </Button>
            <Button
              variant={live ? "default" : "outline"}
              size="sm"
              onClick={() => setLive((v) => !v)}
            >
              <span
                className={cn(
                  "material-symbols-outlined text-base mr-1.5",
                  live && "animate-pulse"
                )}
              >
                {live ? "pause" : "play_arrow"}
              </span>
              {live ? "Pause" : "Live"}
            </Button>
          </div>
        }
      />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 mt-4">
        {/* Source selector */}
        <div className="flex items-center gap-1 bg-muted/50 rounded-lg p-1">
          {SOURCES.map((s) => (
            <button
              key={s.id}
              onClick={() => setSource(s.id)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                source === s.id
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {s.label}
              {sourceStatus[s.id] === false && (
                <span className="ml-1 text-[10px] text-muted-foreground/50">(no log)</span>
              )}
            </button>
          ))}
        </div>

        {/* Level filter */}
        <div className="flex items-center gap-1 bg-muted/50 rounded-lg p-1">
          {LEVELS.map((l) => (
            <button
              key={l}
              onClick={() => setLevel(l)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                level === l
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {l}
            </button>
          ))}
        </div>

        {/* Auto-scroll toggle */}
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-primary"
          />
          Auto-scroll
        </label>

        {!live && (
          <Button
            variant="ghost"
            size="sm"
            onClick={loadSnapshot}
            disabled={loading}
            className="ml-auto"
          >
            <span
              className={cn(
                "material-symbols-outlined text-base mr-1",
                loading && "animate-spin"
              )}
            >
              refresh
            </span>
            Refresh
          </Button>
        )}
      </div>

      {/* Log viewer */}
      <div className="mt-3 rounded-xl overflow-hidden border border-zinc-800">
        {/* Status bar */}
        <div className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border-b border-zinc-800">
          <span
            className={cn(
              "w-2 h-2 rounded-full shrink-0",
              live ? "bg-emerald-500 animate-pulse" : "bg-zinc-600"
            )}
          />
          <span className="text-xs text-zinc-400 font-mono">
            {live ? "LIVE" : "SNAPSHOT"} · arkon-{source} ·{" "}
            {filteredLines.length} lines
          </span>
          {!available && (
            <span className="ml-auto text-xs text-amber-500">
              Log file not found — start the service to generate logs
            </span>
          )}
        </div>

        {/* Log content */}
        <div
          className="h-[600px] overflow-y-auto bg-zinc-950 px-4 py-3 space-y-px"
          onScroll={(e) => {
            const el = e.currentTarget;
            const atBottom =
              el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            if (!atBottom && autoScroll) setAutoScroll(false);
          }}
        >
          {loading && filteredLines.length === 0 ? (
            <div className="flex items-center gap-2 text-zinc-500 text-xs font-mono py-4">
              <span className="material-symbols-outlined text-sm animate-spin">
                progress_activity
              </span>
              Loading logs…
            </div>
          ) : filteredLines.length === 0 ? (
            <div className="text-zinc-600 text-xs font-mono py-4">
              {available
                ? "No log entries match the current filter."
                : "No log file found. Logs appear after the service starts."}
            </div>
          ) : (
            filteredLines.map((line, i) => (
              <LogLine
                key={i}
                raw={line}
                dimmed={
                  level === "ALL" &&
                  (line.includes("| DEBUG   ") || line.includes("| DEBUG    |"))
                }
              />
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </>
  );
}
