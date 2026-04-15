# Agent Instructions — Read Before Every Action

- Read state.md FIRST before touching any code
- Never skip a step in the implementation plan — do them in strict order
- After every working feature: git add -A && git commit -m "feat: description"
- Update state.md after completing each numbered implementation step
- Always run the code and verify it works before marking a step done
- If something fails, fix it completely before moving on — never leave broken code
- Write README.md progressively as you build — not all at once at the end
- Prioritize: correctness first, then full functionality, then visual polish
- The project must look good — use rich terminal formatting, colors, proper UI
- Never leave TODO comments without implementing them in the same step
- Work SLOWLY and CAREFULLY — quality over speed
- A step is NOT done until it runs without errors and looks good

---

# Project: LogFlow Anomaly Engine

**Tagline:** Real-time log-stream anomaly detection with visual blast-radius mapping across service dependency graphs.

**Domain:** Big Data, Data Engineering & Analytics Pipelines

---

## 1. Problem Statement

Modern distributed systems emit thousands of log lines per second across dozens of services. When an incident strikes, on-call engineers spend the first 10 minutes of an outage answering two questions: *what just changed?* and *who else is going to be affected?* Existing log tools (Splunk, ELK, Datadog) excel at search but treat services as independent silos — they do not know that the `payments` outage is about to take down `checkout`, `notifications`, and `analytics-ingest`.

LogFlow Anomaly Engine ingests a live log stream, detects statistical and structural anomalies across multiple algorithms in real time, infers the service dependency graph from the logs themselves, and projects the **blast radius** of each anomaly onto a live D3 force graph — so engineers see at a glance which downstream services will be impacted within the next minute.

---

## 2. Architecture Overview

```
                    ┌────────────────────┐
                    │  Synthetic Log     │  (or external producer)
                    │  Generator         │
                    └─────────┬──────────┘
                              │ LogRecord(JSON)
                              ▼
                    ┌────────────────────┐
                    │  Async Stream Bus  │  (asyncio.Queue, Kafka-shaped API)
                    └─────────┬──────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
       ┌────────────┐  ┌─────────────┐  ┌──────────────┐
       │  DuckDB    │  │  Anomaly    │  │  Service     │
       │  Storage   │  │  Detector   │  │  Graph       │
       │ (columnar) │  │ (3 algos)   │  │  Builder     │
       └─────┬──────┘  └──────┬──────┘  └──────┬───────┘
             │                │                │
             └────────────────┼────────────────┘
                              ▼
                    ┌────────────────────┐
                    │  FastAPI + WS hub  │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │  React/D3 Frontend │
                    │  (live dashboard)  │
                    └────────────────────┘
```

### Anomaly detection layers

1. **Rate-based (statistical)** — rolling Z-score on per-service error/warn rates
2. **Feature-based (ML)** — IsolationForest over numeric feature vectors per minute
3. **Template-based (structural)** — Drain log-template miner detecting brand-new templates

### Blast radius computation

The service-dependency graph is built incrementally from `trace_id` co-occurrence across services in the same time window. When an anomaly fires on service `S`, BFS down the directed graph from `S` produces the impacted set, weighted by edge frequency. The frontend highlights this set with a pulsing ring and labelled hop distance.

---

## 3. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Stream bus | `asyncio.Queue` with Kafka-shaped abstraction | Runs out of the box with zero infra; can be swapped for `confluent-kafka` by replacing one class |
| Storage | DuckDB | Embedded columnar OLAP — same execution model as ClickHouse, ideal for log analytics, no server needed |
| ML | scikit-learn IsolationForest + custom Z-score + Drain | Three complementary detection paradigms |
| API | FastAPI + WebSockets | Native async, perfect for streaming push to UI |
| Frontend | React + TypeScript + Vite | Fast HMR, strict types |
| Styling | Tailwind v4 | Token-based design system, fast iteration |
| Viz | D3.js (force graph + line chart) | Direct SVG control for custom blast-radius animation |

---

## 4. Feature List

### Core
- Synthetic log producer simulating a 12-service e-commerce platform with realistic traces, errors, and latency spikes
- Async pub/sub stream bus with consumer groups
- DuckDB persistence with rolling window queries
- Three anomaly detectors running in parallel
- Auto-built service dependency graph from trace correlation
- Blast-radius BFS with hop weighting
- FastAPI server with `/api/stats`, `/api/graph`, `/api/anomalies`, `/api/logs/recent` and `/ws/stream`
- React dashboard with: live log feed, KPI cards, log volume timeline, service force graph, anomaly panel, blast-radius overlay
- Inject-anomaly button to trigger demo failure scenarios
- Dark theme with neon accent palette

### Stretch
- Drain template tree visualization
- Replay mode (rewind the timeline)
- Per-service detail drawer

---

## 5. File Tree

```
logflow-anomaly-engine/
├── CLAUDE.md
├── README.md
├── state.md
├── .gitignore
├── requirements.txt
├── run.sh                            # one-shot launcher
├── backend/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app, routes, WS, lifespan
│   ├── config.py                     # tunables
│   ├── schemas.py                    # Pydantic models
│   ├── stream_bus.py                 # async pub/sub abstraction
│   ├── generator.py                  # synthetic log generator
│   ├── storage.py                    # DuckDB layer
│   ├── drain.py                      # Drain log-template miner
│   ├── detector.py                   # 3-layer anomaly detector
│   ├── graph.py                      # service dep graph + blast radius
│   └── pipeline.py                   # ties producer→consumer→storage→detector
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── postcss.config.js
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── index.css
        ├── types.ts
        ├── api.ts
        ├── hooks/useLiveStream.ts
        └── components/
            ├── Header.tsx
            ├── KpiBar.tsx
            ├── ServiceGraph.tsx
            ├── LogStream.tsx
            ├── AnomalyPanel.tsx
            ├── TimelineChart.tsx
            └── ScenarioControls.tsx
```

---

## 6. Implementation Steps

1. **Skeleton + deps** — venv, requirements.txt, .gitignore, empty package directories. Verify imports.
2. **Schemas + config** — Pydantic LogRecord, Anomaly, ServiceNode, ServiceEdge; tunable constants.
3. **Synthetic generator** — 12-service topology, realistic traces, error/latency injection knobs.
4. **Stream bus** — async pub/sub with consumer groups; smoke test produce/consume 1k records.
5. **DuckDB storage** — schema, insert batching, rolling-window query helpers; insert + query test.
6. **Drain miner** — fixed-depth log-template tree with similarity match; test on synthetic logs.
7. **Anomaly detector** — Z-score, IsolationForest, Drain-new-template; runs against rolling window.
8. **Service graph** — trace-id co-occurrence builder + BFS blast radius.
9. **Pipeline orchestrator** — runs generator → bus → consumer that writes storage, updates graph, runs detectors.
10. **FastAPI app** — lifespan boot for pipeline; REST endpoints; WebSocket broadcaster.
11. **End-to-end backend smoke** — start API, verify endpoints + WS push.
12. **Frontend scaffold** — Vite React TS + Tailwind dark theme + token CSS variables.
13. **Header + KpiBar + types** — render skeleton.
14. **LogStream component** — live rolling feed with severity coloring.
15. **TimelineChart** — D3 line chart of log volume + anomaly markers.
16. **ServiceGraph** — D3 force layout, blast-radius pulse animation.
17. **AnomalyPanel + ScenarioControls** — click to inject failure scenarios.
18. **Wire WebSocket hook + integrate** — full UI fed by live stream.
19. **README + screenshots placeholder + final polish**.
20. **Final commit & push**.

Each step ends with `git add -A && git commit -m "feat: ..."` after verification.
