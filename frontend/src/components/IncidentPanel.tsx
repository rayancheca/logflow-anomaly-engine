import type { Incident, IncidentState } from "../types";

interface Props {
  incidents: Incident[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onOpenService: (svc: string) => void;
}

const STATE_STYLE: Record<IncidentState, string> = {
  active:    "bg-signal-red/15 text-signal-red border-signal-red/40",
  resolving: "bg-signal-amber/15 text-signal-amber border-signal-amber/40",
  resolved:  "bg-slate-500/10 text-slate-400 border-slate-500/30",
};

function fmtTimeAgo(ts: number): string {
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s ago`;
}

export default function IncidentPanel({ incidents, activeId, onSelect, onOpenService }: Props) {
  const rows = [...incidents].sort(
    (a, b) => (b.state === "active" ? 1 : 0) - (a.state === "active" ? 1 : 0) || b.severity - a.severity,
  );
  return (
    <div className="max-h-[520px] overflow-y-auto scroll-thin space-y-2.5 pr-1">
      {rows.length === 0 && (
        <div className="text-slate-500 text-xs mono py-4">
          no active incidents · inject a scenario to see one form
        </div>
      )}
      {rows.map((inc) => {
        const isActive = inc.id === activeId;
        return (
          <div
            key={inc.id}
            className={`rounded-xl border transition overflow-hidden ${
              isActive
                ? "border-signal-red/50 bg-signal-red/5 shadow-glow"
                : "border-white/5 bg-ink-700/40 hover:border-white/15"
            }`}
          >
            <button
              onClick={() => onSelect(isActive ? null : inc.id)}
              className="w-full text-left px-3 py-2.5 block"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`text-[9px] mono px-1.5 py-[1px] rounded border uppercase tracking-wider ${STATE_STYLE[inc.state]}`}
                  >
                    {inc.state}
                  </span>
                  <span className="mono text-[12px] text-slate-100 font-semibold truncate">
                    {inc.title}
                  </span>
                </div>
                <span className="mono text-[10px] text-slate-500 shrink-0">
                  {fmtTimeAgo(inc.last_ts)}
                </span>
              </div>

              <div className="mt-2 flex items-center gap-3">
                <div className="flex items-center gap-1.5 mono text-[10.5px] text-slate-400">
                  <span className="text-slate-500">root</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenService(inc.root_service);
                    }}
                    className="px-1.5 py-[1px] rounded bg-signal-red/15 text-signal-red border border-signal-red/30 hover:bg-signal-red/25"
                  >
                    {inc.root_service}
                  </button>
                </div>
                <div className="flex items-center gap-1.5 mono text-[10.5px] text-slate-500">
                  <span>{inc.anomaly_count}</span>
                  <span>{inc.anomaly_count === 1 ? "signal" : "signals"}</span>
                </div>
                <div className="flex items-center gap-1.5 mono text-[10.5px] text-slate-500">
                  <span>{inc.impact.length}</span>
                  <span>impacted</span>
                </div>
              </div>

              <div className="mt-2 flex items-center gap-2">
                <div className="h-1 flex-1 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-signal-amber via-signal-red to-signal-violet"
                    style={{ width: `${Math.round(inc.severity * 100)}%` }}
                  />
                </div>
                <span className="mono text-[10px] text-slate-500 tabular-nums">
                  {(inc.severity * 100).toFixed(0)}%
                </span>
              </div>

              <div className="mt-1.5 text-[11px] text-slate-400 leading-snug line-clamp-2">
                {inc.suspected_cause}
              </div>
            </button>

            {isActive && inc.impact.length > 0 && (
              <div className="px-3 pb-3 pt-0">
                <div className="panel-title mb-1.5">blast radius</div>
                <div className="flex flex-wrap gap-1">
                  {inc.impact.slice(0, 14).map((svc) => {
                    const hop = inc.impact_hops[svc] ?? 0;
                    const isRoot = svc === inc.root_service;
                    return (
                      <button
                        key={svc}
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenService(svc);
                        }}
                        className={`text-[10px] mono px-1.5 py-[2px] rounded transition ${
                          isRoot
                            ? "bg-signal-red/25 text-signal-red border border-signal-red/40"
                            : "bg-white/5 text-slate-300 hover:bg-white/10"
                        }`}
                      >
                        {svc}
                        <span className="ml-1 text-signal-red">+{hop}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
