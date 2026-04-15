import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import type { ServiceDetail } from "../types";
import { getServiceDetail } from "../api";

interface Props {
  service: string | null;
  onClose: () => void;
  onOpenTrace: (traceId: string) => void;
}

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toISOString().slice(11, 19);
}

export default function ServiceDrawer({ service, onClose, onOpenTrace }: Props) {
  const [detail, setDetail] = useState<ServiceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const chartRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    async function load() {
      if (!service) return;
      setLoading(true);
      const d = await getServiceDetail(service);
      if (!cancelled) {
        setDetail(d);
        setLoading(false);
      }
    }
    if (service) {
      load();
      interval = setInterval(load, 1500);
    } else {
      setDetail(null);
    }
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [service]);

  useEffect(() => {
    if (!detail || !chartRef.current) return;
    const svg = d3.select(chartRef.current);
    svg.selectAll("*").remove();
    const width = chartRef.current.clientWidth || 500;
    const height = 150;
    const margin = { top: 12, right: 8, bottom: 18, left: 32 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const data = detail.latency_series;
    const x = d3.scaleLinear().domain([0, Math.max(data.length - 1, 1)]).range([0, innerW]);
    const yMax = Math.max(d3.max(data, (d) => d.p99) || 1, 20);
    const y = d3.scaleLinear().domain([0, yMax * 1.1]).nice().range([innerH, 0]);

    const g = svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    g.append("g")
      .selectAll("line")
      .data(y.ticks(4))
      .join("line")
      .attr("x1", 0).attr("x2", innerW)
      .attr("y1", (d) => y(d)).attr("y2", (d) => y(d))
      .attr("stroke", "rgba(255,255,255,0.04)");

    g.append("g")
      .call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(4).tickFormat((d) => `${d}ms`))
      .call((s) => s.select(".domain").remove())
      .call((s) => s.selectAll("text").attr("fill", "#64748b").attr("font-size", 9));

    if (data.length < 2) return;

    const lines: { key: "p50" | "p95" | "p99"; color: string }[] = [
      { key: "p50", color: "#5eead4" },
      { key: "p95", color: "#f59e0b" },
      { key: "p99", color: "#f43f5e" },
    ];
    for (const ln of lines) {
      const line = d3.line<(typeof data)[number]>()
        .x((_, i) => x(i))
        .y((d) => y(d[ln.key]))
        .curve(d3.curveMonotoneX);
      g.append("path").datum(data).attr("d", line).attr("fill", "none")
        .attr("stroke", ln.color).attr("stroke-width", 1.4);
    }

    // legend
    const legend = g.append("g").attr("transform", `translate(${innerW - 100},-2)`);
    lines.forEach((ln, i) => {
      const gp = legend.append("g").attr("transform", `translate(${i * 34},0)`);
      gp.append("circle").attr("cx", 3).attr("cy", 6).attr("r", 2.5).attr("fill", ln.color);
      gp.append("text").attr("x", 9).attr("y", 9).attr("fill", "#94a3b8").attr("font-size", 9).text(ln.key);
    });
  }, [detail]);

  if (!service) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
        onClick={onClose}
      />
      <div className="fixed top-0 right-0 h-full w-full sm:w-[540px] z-50 bg-ink-900/95 border-l border-white/10 shadow-[0_0_80px_-20px_rgba(0,0,0,0.9)] overflow-y-auto scroll-thin">
        <div className="sticky top-0 z-10 px-5 py-4 bg-ink-900/95 backdrop-blur-sm border-b border-white/5 flex items-center justify-between">
          <div>
            <div className="panel-title">service</div>
            <div className="mono font-semibold text-lg text-slate-100">{service}</div>
            {detail && (
              <div className="text-[11px] text-slate-500 mt-0.5 mono">
                group={detail.group} · health={(detail.health * 100).toFixed(0)}%
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg border border-white/10 text-slate-400 hover:text-slate-100 hover:border-white/30 transition"
            aria-label="close"
          >
            ✕
          </button>
        </div>

        {loading && !detail && <div className="p-6 text-slate-500 text-xs mono">loading…</div>}
        {!loading && !detail && (
          <div className="p-6 text-slate-500 text-xs mono">
            no data for this service in the current window
          </div>
        )}

        {detail && (
          <div className="p-5 space-y-5">
            <div className="grid grid-cols-4 gap-3">
              <Stat label="logs / min" value={detail.logs_per_min.toFixed(0)} />
              <Stat label="error %" value={(detail.error_rate * 100).toFixed(1)}
                tone={detail.error_rate > 0.05 ? "bad" : detail.error_rate > 0.02 ? "warn" : "ok"} />
              <Stat label="mean ms" value={detail.mean_latency_ms.toFixed(0)} />
              <Stat label="p95 ms" value={detail.p95_latency_ms.toFixed(0)}
                tone={detail.p95_latency_ms > 300 ? "warn" : "ok"} />
            </div>

            <section>
              <div className="panel-title mb-1.5">latency p50 / p95 / p99 · last 60s</div>
              <div className="rounded-lg bg-ink-800/60 border border-white/5 px-2 py-2">
                <svg ref={chartRef} className="w-full h-[150px]" />
              </div>
            </section>

            <section>
              <div className="panel-title mb-1.5">forecast · next window</div>
              <div className="rounded-lg bg-ink-800/60 border border-white/5 p-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="mono text-[11px] text-slate-500">predicted error rate</span>
                  <span className="mono text-lg font-semibold text-accent-400">
                    {(detail.forecast_error_rate * 100).toFixed(2)}%
                  </span>
                  <span className="mono text-[10px] text-slate-500">
                    ±{(detail.forecast_stddev * 100).toFixed(1)}
                  </span>
                </div>
                <div className="mono text-[10px] text-slate-500">EWMA α=0.35</div>
              </div>
            </section>

            <div className="grid grid-cols-2 gap-3">
              <section>
                <div className="panel-title mb-1.5">upstream · callers</div>
                <div className="rounded-lg bg-ink-800/60 border border-white/5 p-2 space-y-1">
                  {detail.upstream.length === 0 && (
                    <div className="text-[11px] text-slate-600 mono">entry point</div>
                  )}
                  {detail.upstream.map((e) => (
                    <div key={`${e.source}-${e.target}`} className="flex items-center justify-between text-[11px] mono">
                      <span className="text-slate-300">{e.source}</span>
                      <span className="text-slate-600">w {e.weight.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section>
                <div className="panel-title mb-1.5">downstream · callees</div>
                <div className="rounded-lg bg-ink-800/60 border border-white/5 p-2 space-y-1">
                  {detail.downstream.length === 0 && (
                    <div className="text-[11px] text-slate-600 mono">leaf</div>
                  )}
                  {detail.downstream.map((e) => (
                    <div key={`${e.source}-${e.target}`} className="flex items-center justify-between text-[11px] mono">
                      <span className="text-slate-300">{e.target}</span>
                      <span className="text-slate-600">w {e.weight.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <section>
              <div className="panel-title mb-1.5">top templates · last 60s</div>
              <div className="rounded-lg bg-ink-800/60 border border-white/5 divide-y divide-white/5">
                {detail.top_templates.length === 0 && (
                  <div className="text-[11px] text-slate-600 mono p-3">no templates</div>
                )}
                {detail.top_templates.map((t) => (
                  <div key={t.template_id} className="flex items-center justify-between gap-2 px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[9px] mono px-1 rounded bg-white/5 text-slate-500 shrink-0">
                        #{t.template_id}
                      </span>
                      <span className="mono text-[11px] text-slate-300 truncate">{t.template}</span>
                    </div>
                    <span className="mono text-[10px] text-slate-500 shrink-0">{t.count}</span>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="panel-title mb-1.5">recent errors / warnings</div>
              <div className="rounded-lg bg-ink-800/60 border border-white/5 divide-y divide-white/5">
                {detail.recent_errors.length === 0 && (
                  <div className="text-[11px] text-slate-600 mono p-3">
                    no errors in the current window — all green.
                  </div>
                )}
                {detail.recent_errors.map((e, i) => (
                  <button
                    key={`${e.trace_id}-${i}`}
                    onClick={() => onOpenTrace(e.trace_id)}
                    className="w-full text-left px-3 py-2 hover:bg-white/[0.03] transition"
                  >
                    <div className="flex items-center gap-2 mono text-[10.5px]">
                      <span className="text-slate-600">{fmtTs(e.ts)}</span>
                      <span
                        className={`px-1 rounded ${
                          e.level === "ERROR" || e.level === "FATAL"
                            ? "bg-signal-red/15 text-signal-red"
                            : "bg-signal-amber/15 text-signal-amber"
                        }`}
                      >
                        {e.level}
                      </span>
                      <span className="text-slate-500">{e.latency_ms.toFixed(0)}ms</span>
                      <span className="text-slate-600 ml-auto">open trace →</span>
                    </div>
                    <div className="text-[11px] text-slate-300 mt-0.5 truncate">{e.message}</div>
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </>
  );
}

function Stat({ label, value, tone = "ok" }: { label: string; value: string; tone?: "ok" | "warn" | "bad" }) {
  const color =
    tone === "bad" ? "text-signal-red"
    : tone === "warn" ? "text-signal-amber"
    : "text-accent-400";
  return (
    <div className="rounded-lg bg-ink-800/60 border border-white/5 px-2 py-2">
      <div className="panel-title">{label}</div>
      <div className={`mt-1 text-xl font-semibold mono ${color}`}>{value}</div>
    </div>
  );
}
