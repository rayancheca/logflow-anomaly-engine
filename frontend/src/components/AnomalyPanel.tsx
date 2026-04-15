import type { Anomaly, AnomalyKind } from "../types";

interface Props {
  anomalies: Anomaly[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
}

const KIND_LABEL: Record<AnomalyKind, string> = {
  rate_spike:       "RATE",
  feature_outlier:  "IFOREST",
  new_template:     "NEW TMPL",
};

const KIND_STYLE: Record<AnomalyKind, string> = {
  rate_spike:      "bg-signal-red/10 text-signal-red border-signal-red/30",
  feature_outlier: "bg-signal-violet/10 text-signal-violet border-signal-violet/30",
  new_template:    "bg-signal-amber/10 text-signal-amber border-signal-amber/30",
};

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

export default function AnomalyPanel({ anomalies, activeId, onSelect }: Props) {
  const rows = [...anomalies].reverse();
  return (
    <div className="max-h-[420px] overflow-y-auto scroll-thin space-y-2 pr-1">
      {rows.length === 0 && (
        <div className="text-slate-500 text-xs mono py-3">no anomalies yet · click a scenario to inject one</div>
      )}
      {rows.map((a) => {
        const isActive = a.id === activeId;
        return (
          <button
            key={a.id}
            onClick={() => onSelect(isActive ? null : a.id)}
            className={`w-full text-left block rounded-lg border transition px-3 py-2.5 ${
              isActive
                ? "bg-signal-red/5 border-signal-red/40"
                : "bg-ink-700/50 border-white/5 hover:border-white/10"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`text-[9px] mono px-1.5 py-[1px] rounded border ${KIND_STYLE[a.kind]}`}>
                  {KIND_LABEL[a.kind]}
                </span>
                <span className="mono text-[12px] text-slate-100 font-semibold">{a.service}</span>
              </div>
              <span className="mono text-[10px] text-slate-500">{fmtTs(a.ts)}</span>
            </div>
            <div className="mt-1.5 text-[11.5px] text-slate-300 leading-snug">{a.description}</div>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-signal-amber to-signal-red"
                  style={{ width: `${Math.round(a.severity * 100)}%` }}
                />
              </div>
              <span className="mono text-[10px] text-slate-500 tabular-nums">
                {(a.severity * 100).toFixed(0)}%
              </span>
            </div>
            {a.blast_radius.length > 1 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {a.blast_radius.slice(0, 8).map((svc) => {
                  const hop = a.blast_hops[svc] ?? 0;
                  return (
                    <span
                      key={svc}
                      className="text-[10px] mono px-1.5 py-[1px] rounded bg-white/5 text-slate-300"
                    >
                      {svc}
                      <span className="text-signal-red ml-1">+{hop}</span>
                    </span>
                  );
                })}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
