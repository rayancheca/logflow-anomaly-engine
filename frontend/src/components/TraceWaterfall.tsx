import { useEffect, useState } from "react";
import type { Trace } from "../types";
import { getTrace } from "../api";

interface Props {
  traceId: string | null;
  onClose: () => void;
}

const SVC_COLORS = [
  "#5eead4", "#60a5fa", "#a855f7", "#f59e0b", "#f43f5e",
  "#06b6d4", "#84cc16", "#e879f9", "#fb923c", "#22d3ee",
];

function colorFor(svc: string, services: string[]): string {
  const idx = services.indexOf(svc);
  return SVC_COLORS[idx % SVC_COLORS.length];
}

export default function TraceWaterfall({ traceId, onClose }: Props) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!traceId) return;
      setLoading(true);
      setError(null);
      const t = await getTrace(traceId);
      if (cancelled) return;
      setLoading(false);
      if (!t) setError("trace not found in the current window");
      else setTrace(t);
    }
    if (traceId) {
      setTrace(null);
      load();
    } else {
      setTrace(null);
    }
    return () => { cancelled = true; };
  }, [traceId]);

  if (!traceId) return null;

  const totalMs = trace?.duration_ms || 1;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40"
        onClick={onClose}
      />
      <div
        className="fixed top-[6%] left-1/2 -translate-x-1/2 w-[95%] max-w-[1100px] max-h-[85vh] z-50 rounded-2xl bg-ink-900/95 border border-white/10 shadow-[0_40px_80px_-20px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
          <div>
            <div className="panel-title">trace waterfall</div>
            <div className="mono text-[13px] text-slate-100 mt-0.5">
              {traceId}
              {trace && (
                <span className="text-slate-500 ml-3 text-[11px]">
                  {trace.spans.length} spans · {trace.duration_ms.toFixed(1)}ms · {trace.services.length} services
                  {trace.has_errors && <span className="ml-2 text-signal-red">· errors</span>}
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg border border-white/10 text-slate-400 hover:text-slate-100 hover:border-white/30 transition"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scroll-thin p-5">
          {loading && <div className="text-slate-500 text-xs mono">loading trace…</div>}
          {error && <div className="text-signal-red text-xs mono">{error}</div>}
          {trace && (
            <>
              <div className="mb-4 flex flex-wrap gap-2">
                {trace.services.map((s) => (
                  <span
                    key={s}
                    className="mono text-[10px] px-1.5 py-[1px] rounded border"
                    style={{ borderColor: colorFor(s, trace.services), color: colorFor(s, trace.services) }}
                  >
                    {s}
                  </span>
                ))}
              </div>
              <div className="space-y-1.5">
                {trace.spans.map((span, i) => {
                  const rel = (span.ts - trace.started) * 1000; // ms offset
                  const leftPct = Math.max(0, Math.min(100, (rel / totalMs) * 100));
                  const widthPct = Math.max(
                    1.2,
                    Math.min(100 - leftPct, (span.latency_ms / totalMs) * 100),
                  );
                  const color = colorFor(span.service, trace.services);
                  const isError = span.level === "ERROR" || span.level === "FATAL";
                  return (
                    <div key={`${span.span_id}-${i}`} className="group">
                      <div className="flex items-center gap-2 text-[10.5px] mono">
                        <span className="w-[90px] truncate" style={{ color }}>
                          {span.service}
                        </span>
                        <div className="relative flex-1 h-5 bg-white/[0.03] rounded">
                          <div
                            className={`absolute top-0 bottom-0 rounded ${isError ? "ring-1 ring-signal-red" : ""}`}
                            style={{
                              left: `${leftPct}%`,
                              width: `${widthPct}%`,
                              background: `linear-gradient(90deg, ${color}66, ${color}22)`,
                              borderLeft: `2px solid ${color}`,
                            }}
                          />
                          <div
                            className="absolute top-0 bottom-0 flex items-center pointer-events-none"
                            style={{ left: `${leftPct}%` }}
                          >
                            <span className="text-[10px] text-slate-200 ml-1.5 drop-shadow">
                              {span.latency_ms.toFixed(1)}ms
                            </span>
                          </div>
                        </div>
                        <span className="w-[48px] text-right text-slate-600">{span.status_code}</span>
                      </div>
                      <div className="ml-[90px] mt-0.5 text-[11px] text-slate-400 truncate">
                        {span.message}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
