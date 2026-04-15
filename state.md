## Status
COMPLETE (v2)

## Project
logflow-anomaly-engine — Real-time log-stream anomaly detection with
incident correlation and visual blast-radius mapping across service
dependency graphs.

## Session count
2

## Summary (v2 expansion)
The v2 session doubled the project scope. Backend now clusters raw
anomalies into ranked incidents, exposes deep-dive REST endpoints for
traces / services / templates / search / correlations / rules, runs a
live alert-rules engine, forecasts per-service error rates (EWMA), and
exports Prometheus metrics. The generator injects realistic downstream
cascade effects per scenario so the correlation engine has something
non-trivial to work with. The frontend gained six new interactive views:
IncidentPanel, ServiceDrawer, TraceWaterfall modal, TemplateExplorer,
CorrelationHeatmap, SearchBar, and RulesManager — all wired together in
a restructured four-row dashboard with a chaos banner, click-through
service drawer, and click-through trace waterfall.

Verified end-to-end: backend smoke tests + REST endpoint probes + full
headless-Chrome screenshots of the running dashboard with active
scenarios and correct root-cause ranking (payments_outage correctly
ranks `payments` as root, not the caller `checkout`).

## Completed steps (v2)
- schemas: Incident, AlertRule, TraceSpan, Trace, ServiceDetail,
  TemplateInfo, CorrelationMatrix, SearchResult, ServiceLatencyPoint
- incidents.py: clustering + reverse-BFS root ranking + state machine
- rules.py: dwell-time rule engine + CRUD + three defaults
- forecast.py: EWMA + running variance
- generator.py: cascading downstream scenarios + 7 scenario catalog
- storage.py: trace fetch, search, per-service latency series, top
  templates per service, template aggregates, error-rate matrix
- pipeline.py: incident engine + rules + forecaster + correlation loop +
  prometheus export
- main.py: 15 REST endpoints (traces, service, templates, search,
  correlations, rules CRUD, incidents, /metrics)
- frontend types + api client
- IncidentPanel, ServiceDrawer, TraceWaterfall, TemplateExplorer,
  CorrelationHeatmap, SearchBar, RulesManager components
- ServiceGraph extended with onNodeClick → service drawer
- KpiBar extended with active_incidents card (6 total)
- App.tsx fully restructured into a 4-row layout with chaos banner,
  drawers, modals
- README v2 rewrite with full feature list + API reference
- Screenshot `docs/dashboard.png` refreshed with v2 UI

## Blockers
None.

## Notes
Run with `./run.sh`. Backend on :8766, frontend on :5174.
