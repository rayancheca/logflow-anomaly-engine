import { useLiveStream } from "./hooks/useLiveStream";
import Header from "./components/Header";
import KpiBar from "./components/KpiBar";
import LogStream from "./components/LogStream";
import AnomalyPanel from "./components/AnomalyPanel";
import ServiceGraph from "./components/ServiceGraph";
import TimelineChart from "./components/TimelineChart";
import ScenarioControls from "./components/ScenarioControls";
import { useMemo, useState } from "react";

export default function App() {
  const { data, connected } = useLiveStream("/ws/stream");
  const [focusAnomaly, setFocusAnomaly] = useState<string | null>(null);

  const activeAnomaly = useMemo(() => {
    if (!data) return null;
    if (focusAnomaly) {
      const found = data.anomalies.find((a) => a.id === focusAnomaly);
      if (found) return found;
    }
    return data.anomalies[data.anomalies.length - 1] ?? null;
  }, [data, focusAnomaly]);

  return (
    <div className="min-h-screen text-slate-100 grid-bg">
      <Header connected={connected} uptime={data?.kpi.uptime_seconds ?? 0} />
      <main className="max-w-[1600px] mx-auto px-6 pb-10">
        <KpiBar kpi={data?.kpi ?? null} />
        <div className="mt-5 grid grid-cols-12 gap-5">
          <section className="col-span-12 xl:col-span-8 panel p-4 min-h-[460px]">
            <div className="flex items-center justify-between mb-3">
              <div className="panel-title">Service dependency graph · blast radius</div>
              {activeAnomaly && (
                <div className="mono text-[11px] text-signal-amber">
                  active: <span className="text-slate-200">{activeAnomaly.service}</span>
                  <span className="text-slate-500"> · </span>
                  {activeAnomaly.kind.replace("_", " ")}
                </div>
              )}
            </div>
            <ServiceGraph
              graph={data?.graph ?? { nodes: [], edges: [] }}
              anomaly={activeAnomaly}
            />
          </section>
          <section className="col-span-12 xl:col-span-4 panel p-4 flex flex-col gap-4">
            <div>
              <div className="panel-title mb-2">Log volume · last 60s</div>
              <TimelineChart timeline={data?.timeline ?? []} />
            </div>
            <ScenarioControls />
          </section>

          <section className="col-span-12 xl:col-span-8 panel p-4">
            <div className="panel-title mb-3">Live log stream</div>
            <LogStream logs={data?.logs ?? []} highlightService={activeAnomaly?.service ?? null} />
          </section>

          <section className="col-span-12 xl:col-span-4 panel p-4">
            <div className="panel-title mb-3">Detected anomalies</div>
            <AnomalyPanel
              anomalies={data?.anomalies ?? []}
              activeId={activeAnomaly?.id ?? null}
              onSelect={setFocusAnomaly}
            />
          </section>
        </div>
        <footer className="mt-8 flex items-center justify-between text-[11px] text-slate-500">
          <span>LogFlow · DuckDB · IsolationForest · Drain · FastAPI · D3</span>
          <span className="mono">window {data?.kpi.window_seconds ?? 60}s · {data?.kpi.templates_tracked ?? 0} templates</span>
        </footer>
      </main>
    </div>
  );
}
