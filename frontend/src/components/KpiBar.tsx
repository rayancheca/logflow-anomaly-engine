import type { Kpi } from "../types";

interface Props {
  kpi: Kpi | null;
}

interface Card {
  label: string;
  value: string;
  sub: string;
  tone: "default" | "good" | "warn" | "bad" | "info";
}

function toneClass(t: Card["tone"]): string {
  switch (t) {
    case "good": return "text-signal-green";
    case "warn": return "text-signal-amber";
    case "bad":  return "text-signal-red";
    case "info": return "text-signal-cyan";
    default:     return "text-accent-400";
  }
}

export default function KpiBar({ kpi }: Props) {
  const cards: Card[] = [
    {
      label: "logs / sec",
      value: kpi ? kpi.logs_per_sec.toFixed(1) : "—",
      sub: "rolling window",
      tone: "default",
    },
    {
      label: "error rate",
      value: kpi ? `${(kpi.error_rate * 100).toFixed(2)}%` : "—",
      sub: "of ingested logs",
      tone: kpi && kpi.error_rate > 0.05 ? "bad" : kpi && kpi.error_rate > 0.02 ? "warn" : "good",
    },
    {
      label: "active services",
      value: kpi ? String(kpi.active_services) : "—",
      sub: "emitting this window",
      tone: "info",
    },
    {
      label: "incidents",
      value: kpi ? String(kpi.active_incidents) : "—",
      sub: "correlated clusters",
      tone: kpi && kpi.active_incidents > 0 ? "bad" : "good",
    },
    {
      label: "anomalies · 60s",
      value: kpi ? String(kpi.anomalies_last_min) : "—",
      sub: "across all detectors",
      tone: kpi && kpi.anomalies_last_min > 4 ? "bad" : kpi && kpi.anomalies_last_min > 0 ? "warn" : "good",
    },
    {
      label: "templates",
      value: kpi ? String(kpi.templates_tracked) : "—",
      sub: "drain tree leaves",
      tone: "info",
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mt-6">
      {cards.map((c) => (
        <div key={c.label} className="panel p-4 relative overflow-hidden">
          <div className="absolute -right-10 -top-10 w-32 h-32 rounded-full bg-gradient-to-br from-white/[0.03] to-transparent blur-2xl pointer-events-none" />
          <div className="panel-title">{c.label}</div>
          <div className={`mt-2 text-[28px] font-semibold mono leading-none ${toneClass(c.tone)}`}>
            {c.value}
          </div>
          <div className="text-[11px] text-slate-500 mt-2">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}
