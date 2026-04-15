import { useMemo, useState } from "react";
import { useLiveStream } from "./hooks/useLiveStream";
import Header from "./components/Header";
import KpiBar from "./components/KpiBar";
import LogStream from "./components/LogStream";
import IncidentPanel from "./components/IncidentPanel";
import ServiceGraph from "./components/ServiceGraph";
import TimelineChart from "./components/TimelineChart";
import ScenarioControls from "./components/ScenarioControls";
import ServiceDrawer from "./components/ServiceDrawer";
import TraceWaterfall from "./components/TraceWaterfall";
import TemplateExplorer from "./components/TemplateExplorer";
import CorrelationHeatmap from "./components/CorrelationHeatmap";
import SearchBar from "./components/SearchBar";
import RulesManager from "./components/RulesManager";

export default function App() {
  const { data, connected } = useLiveStream("/ws/stream");
  const [focusIncident, setFocusIncident] = useState<string | null>(null);
  const [drawerService, setDrawerService] = useState<string | null>(null);
  const [waterfallTraceId, setWaterfallTraceId] = useState<string | null>(null);
  const [rulesNonce, setRulesNonce] = useState(0);

  const activeIncident = useMemo(() => {
    if (!data) return null;
    if (focusIncident) {
      const found = data.incidents.find((i) => i.id === focusIncident);
      if (found) return found;
    }
    const actives = data.incidents.filter((i) => i.state !== "resolved");
    if (actives.length === 0) return null;
    return actives.reduce((a, b) => (b.severity > a.severity ? b : a));
  }, [data, focusIncident]);

  const services = useMemo(
    () => data?.graph.nodes.map((n) => n.id).sort() ?? [],
    [data],
  );

  const rules = data?.rules ?? [];
  const refreshRules = () => setRulesNonce((n) => n + 1);
  void rulesNonce;

  return (
    <div className="min-h-screen text-slate-100 grid-bg">
      <Header connected={connected} uptime={data?.kpi.uptime_seconds ?? 0} />

      {data && data.active_scenarios.length > 0 && (
        <div className="bg-signal-amber/5 border-b border-signal-amber/20">
          <div className="max-w-[1600px] mx-auto px-6 py-2 flex items-center gap-3 text-[11px] mono">
            <span className="text-signal-amber uppercase tracking-wider">chaos active</span>
            <span className="text-slate-400">
              scenario effects live on{" "}
              {data.active_scenarios.map((s, i) => (
                <span key={s}>
                  <button
                    onClick={() => setDrawerService(s)}
                    className="text-signal-amber hover:underline"
                  >
                    {s}
                  </button>
                  {i < data.active_scenarios.length - 1 && <span className="text-slate-600">, </span>}
                </span>
              ))}
            </span>
          </div>
        </div>
      )}

      <main className="max-w-[1600px] mx-auto px-6 pb-12">
        <KpiBar kpi={data?.kpi ?? null} />

        {/* Row 1: graph + right column */}
        <div className="mt-5 grid grid-cols-12 gap-5">
          <section id="graph" className="col-span-12 xl:col-span-8 panel p-4 min-h-[480px]">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="panel-title">service dependency graph</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  click a node to open the service drawer · red edges = blast radius of the active incident
                </div>
              </div>
              {activeIncident && (
                <div className="mono text-[11px] text-right">
                  <div className="text-signal-red">
                    incident · root <span className="text-slate-100">{activeIncident.root_service}</span>
                  </div>
                  <div className="text-slate-500">
                    {activeIncident.impact.length} impacted · {activeIncident.anomaly_count} signals
                  </div>
                </div>
              )}
            </div>
            <ServiceGraph
              graph={data?.graph ?? { nodes: [], edges: [] }}
              incident={activeIncident}
              onNodeClick={setDrawerService}
            />
          </section>

          <section className="col-span-12 xl:col-span-4 panel p-4 flex flex-col gap-5">
            <div>
              <div className="panel-title mb-2">log volume · last 60s</div>
              <TimelineChart timeline={data?.timeline ?? []} />
            </div>
            <ScenarioControls />
          </section>
        </div>

        {/* Row 2: incidents + live logs */}
        <div className="mt-5 grid grid-cols-12 gap-5">
          <section id="incidents" className="col-span-12 xl:col-span-5 panel p-4">
            <div className="panel-title mb-3">active incidents</div>
            <IncidentPanel
              incidents={data?.incidents ?? []}
              activeId={activeIncident?.id ?? null}
              onSelect={setFocusIncident}
              onOpenService={setDrawerService}
            />
          </section>
          <section className="col-span-12 xl:col-span-7 panel p-4">
            <div className="panel-title mb-3">live log stream</div>
            <LogStream
              logs={data?.logs ?? []}
              highlightService={activeIncident?.root_service ?? null}
            />
          </section>
        </div>

        {/* Row 3: search + correlation */}
        <div className="mt-5 grid grid-cols-12 gap-5">
          <section id="search" className="col-span-12 xl:col-span-7 panel p-4">
            <div className="panel-title mb-3">log search · rolling window</div>
            <SearchBar
              services={services}
              onOpenTrace={setWaterfallTraceId}
              onOpenService={setDrawerService}
            />
          </section>
          <section id="correlation" className="col-span-12 xl:col-span-5 panel p-4">
            <CorrelationHeatmap />
          </section>
        </div>

        {/* Row 4: templates + rules */}
        <div className="mt-5 grid grid-cols-12 gap-5">
          <section id="templates" className="col-span-12 xl:col-span-7 panel p-4">
            <TemplateExplorer services={services} />
          </section>
          <section id="rules" className="col-span-12 xl:col-span-5 panel p-4">
            <RulesManager
              rules={rules}
              services={services}
              onChanged={refreshRules}
            />
          </section>
        </div>

        <footer className="mt-8 flex items-center justify-between text-[11px] text-slate-500">
          <span>LogFlow · DuckDB · IsolationForest · Drain · FastAPI · D3 · incident correlation</span>
          <span className="mono">
            window {data?.kpi.window_seconds ?? 60}s · {data?.kpi.templates_tracked ?? 0} templates ·{" "}
            {data?.kpi.active_incidents ?? 0} active
          </span>
        </footer>
      </main>

      <ServiceDrawer
        service={drawerService}
        onClose={() => setDrawerService(null)}
        onOpenTrace={(tid) => {
          setDrawerService(null);
          setWaterfallTraceId(tid);
        }}
      />
      <TraceWaterfall
        traceId={waterfallTraceId}
        onClose={() => setWaterfallTraceId(null)}
      />
    </div>
  );
}
