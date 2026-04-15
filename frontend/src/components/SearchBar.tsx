import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchResult, Severity } from "../types";
import { searchLogs } from "../api";

interface Props {
  services: string[];
  onOpenTrace: (traceId: string) => void;
  onOpenService: (svc: string) => void;
}

const LEVELS: (Severity | "*")[] = ["*", "INFO", "WARN", "ERROR", "DEBUG"];

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(11, 23);
}

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: "text-slate-500",
  INFO:  "text-signal-cyan",
  WARN:  "text-signal-amber",
  ERROR: "text-signal-red",
  FATAL: "text-signal-red",
};

export default function SearchBar({ services, onOpenTrace, onOpenService }: Props) {
  const [q, setQ] = useState("");
  const [service, setService] = useState<string>("*");
  const [level, setLevel] = useState<string>("*");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await searchLogs({
          q,
          service: service === "*" ? undefined : service,
          level:   level === "*" ? undefined : level,
          limit: 60,
        });
        setResult(r);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [q, service, level]);

  const shown = result?.hits ?? [];
  const summary = useMemo(() => {
    if (!result) return "";
    return `${result.hits.length} of ${result.total_scanned} matching · ${result.window_seconds}s window`;
  }, [result]);

  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="search logs… (e.g. 'timeout', 'sku_', 'declined')"
          className="flex-1 min-w-[220px] bg-ink-700/60 border border-white/10 rounded-lg px-3 py-2 text-[12px] mono text-slate-200 placeholder:text-slate-600 outline-none focus:border-accent-500/50"
        />
        <select
          value={service}
          onChange={(e) => setService(e.target.value)}
          className="bg-ink-700/60 border border-white/10 rounded-lg px-2 py-2 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
        >
          <option value="*">all services</option>
          {services.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="bg-ink-700/60 border border-white/10 rounded-lg px-2 py-2 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
        >
          {LEVELS.map((l) => (
            <option key={l} value={l}>{l === "*" ? "all levels" : l}</option>
          ))}
        </select>
      </div>
      <div className="flex items-center justify-between text-[10.5px] mono text-slate-500 mb-2">
        <span>{summary}</span>
        {loading && <span>…</span>}
      </div>
      <div className="rounded-lg border border-white/5 bg-ink-800/40 divide-y divide-white/5 max-h-[280px] overflow-y-auto scroll-thin">
        {shown.length === 0 && (
          <div className="text-[11px] text-slate-600 mono p-3">
            {q ? "no matches" : "type something to search the rolling window"}
          </div>
        )}
        {shown.map((h, i) => (
          <div
            key={`${h.trace_id}-${h.ts}-${i}`}
            className="flex items-start gap-3 px-3 py-1.5 hover:bg-white/[0.03] transition mono text-[11px]"
          >
            <span className="text-slate-600 w-[80px] shrink-0">{fmtTs(h.ts)}</span>
            <span
              className={`shrink-0 w-[40px] text-[9px] uppercase tracking-wider ${LEVEL_STYLE[h.level]}`}
            >
              {h.level}
            </span>
            <button
              onClick={() => onOpenService(h.service)}
              className="shrink-0 w-[110px] truncate text-left text-accent-400 hover:underline"
            >
              {h.service}
            </button>
            <span className="shrink-0 w-[44px] text-right text-slate-600">
              {h.latency_ms.toFixed(0)}ms
            </span>
            <span className="flex-1 truncate text-slate-300">{h.message}</span>
            <button
              onClick={() => onOpenTrace(h.trace_id)}
              className="text-[10px] text-slate-500 hover:text-slate-200 shrink-0"
            >
              trace →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
