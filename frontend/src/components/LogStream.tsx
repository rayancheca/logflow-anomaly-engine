import { useMemo } from "react";
import type { LogRecord, Severity } from "../types";

interface Props {
  logs: LogRecord[];
  highlightService: string | null;
}

const LEVEL_STYLE: Record<Severity, string> = {
  DEBUG: "text-slate-500",
  INFO:  "text-signal-cyan",
  WARN:  "text-signal-amber",
  ERROR: "text-signal-red",
  FATAL: "text-signal-red",
};

const LEVEL_TAG: Record<Severity, string> = {
  DEBUG: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  INFO:  "bg-signal-cyan/10 text-signal-cyan border-signal-cyan/20",
  WARN:  "bg-signal-amber/10 text-signal-amber border-signal-amber/20",
  ERROR: "bg-signal-red/15 text-signal-red border-signal-red/30",
  FATAL: "bg-signal-red/25 text-signal-red border-signal-red/40",
};

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toISOString().slice(11, 23);
}

export default function LogStream({ logs, highlightService }: Props) {
  const rows = useMemo(() => [...logs].reverse(), [logs]);
  return (
    <div className="relative">
      <div className="max-h-[360px] overflow-y-auto scroll-thin space-y-[3px] pr-1">
        {rows.length === 0 && (
          <div className="text-slate-500 text-xs mono">waiting for log stream…</div>
        )}
        {rows.map((l, i) => {
          const isHi = highlightService && l.service === highlightService;
          return (
            <div
              key={`${l.trace_id}-${l.span_id}-${i}`}
              className={`flex items-start gap-3 text-[11.5px] mono leading-5 py-1 px-2 rounded ${
                isHi ? "bg-signal-red/5 ring-1 ring-signal-red/30" : "hover:bg-white/[0.02]"
              }`}
            >
              <span className="text-slate-600 w-[80px] shrink-0">{fmtTs(l.ts)}</span>
              <span
                className={`shrink-0 px-1.5 py-[1px] border rounded text-[10px] uppercase tracking-wider ${LEVEL_TAG[l.level]}`}
              >
                {l.level}
              </span>
              <span className="shrink-0 w-[110px] truncate text-accent-400">{l.service}</span>
              <span className="shrink-0 w-[46px] text-right text-slate-500">
                {l.latency_ms.toFixed(0)}ms
              </span>
              <span className={`truncate ${LEVEL_STYLE[l.level]}`}>{l.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
