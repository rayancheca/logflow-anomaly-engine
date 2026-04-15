import { useEffect, useState } from "react";
import { listScenarios, triggerScenario } from "../api";

export default function ScenarioControls() {
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [fired, setFired] = useState<string | null>(null);

  useEffect(() => {
    listScenarios()
      .then((d) => setScenarios(d.scenarios))
      .catch(() => setScenarios([]));
  }, []);

  async function fire(name: string) {
    setPending(name);
    const ok = await triggerScenario(name);
    setPending(null);
    if (ok) {
      setFired(name);
      setTimeout(() => setFired((f) => (f === name ? null : f)), 2200);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="panel-title">Inject failure scenario</div>
        <span className="text-[10px] mono text-slate-600">TTL 20–30s</span>
      </div>
      <div className="grid grid-cols-1 gap-1.5">
        {scenarios.map((s) => {
          const label = s.replace(/_/g, " ");
          const isPending = pending === s;
          const isFired = fired === s;
          return (
            <button
              key={s}
              disabled={isPending}
              onClick={() => fire(s)}
              className={`group flex items-center justify-between text-left px-3 py-2 rounded-lg border transition ${
                isFired
                  ? "border-accent-500/60 bg-accent-500/10"
                  : "border-white/5 bg-ink-700/40 hover:bg-ink-700/80 hover:border-white/15"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full ${isFired ? "bg-accent-500 animate-pulse" : "bg-slate-600 group-hover:bg-signal-amber"}`} />
                <span className="mono text-[12px] capitalize">{label}</span>
              </div>
              <span className="text-[10px] mono text-slate-500 group-hover:text-signal-amber">
                {isPending ? "…" : isFired ? "FIRED" : "RUN"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
