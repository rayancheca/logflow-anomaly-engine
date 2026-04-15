# LogFlow · Anomaly Engine

> Real-time log-stream anomaly detection with visual blast-radius mapping across service dependency graphs.

![dashboard](docs/dashboard.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab.svg)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5.5-3178c6.svg)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/duckdb-1.5-fff000.svg)](https://duckdb.org/)
[![License](https://img.shields.io/badge/license-MIT-slate.svg)](LICENSE)

---

## Why this exists

Modern distributed systems emit thousands of log lines per second. When an
incident hits, on-call engineers spend the first ten minutes of an outage
answering two questions: *what just changed?* and *who else is about to be
affected?*

Off-the-shelf log tools (Splunk, ELK, Datadog) answer the first question well,
but treat services as independent silos. They will tell you that `payments` is
erroring, but they will not tell you that `checkout`, `ledger`, and
`notifications` are the next three things that are going to page.

**LogFlow Anomaly Engine** is a standalone demo of what a blast-radius-aware
log engine looks like. It ingests a live log stream, runs three anomaly
detectors in parallel, infers the service dependency graph **from the logs
themselves**, and projects the downstream impact of each anomaly onto a live
D3 force graph — so one glance is enough to see who is about to get hit.

---

## What it does

- **Ingests a synthetic 12-service e-commerce log stream** through an
  in-process Kafka-shaped bus at ~60–220 lines/sec.
- **Persists logs in a columnar DuckDB store** and runs rolling-window
  aggregations on every detection tick.
- **Runs three parallel anomaly detectors**:
  - Rolling **Z-score** over per-service error and latency rates.
  - **IsolationForest** (scikit-learn) over multi-dimensional service feature
    vectors.
  - **Drain** log-template miner detecting brand-new templates after warmup.
- **Builds a directed service dependency graph** incrementally from
  `trace_id` / `parent_service` co-occurrence, with exponential edge decay.
- **Computes the blast radius** of each anomaly via a weighted BFS and
  annotates each downstream service with its hop distance.
- **Broadcasts everything over a WebSocket** to a React + D3 dashboard with
  live KPIs, a rolling log feed, a timeline chart, an interactive service
  graph with pulse-ring highlight, and five one-click failure injectors.

---

## Quickstart

```bash
git clone https://github.com/rayancheca/logflow-anomaly-engine.git
cd logflow-anomaly-engine
./run.sh
# → backend  http://127.0.0.1:8766
# → frontend http://127.0.0.1:5174
```

The `run.sh` launcher creates the Python venv, installs dependencies, boots
FastAPI, then boots Vite. Open the frontend URL in a browser.

### Manual setup

```bash
# backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8766

# frontend
cd frontend
npm install
npm run dev
```

### Trigger a scenario

Click any button under **Inject failure scenario**. Options:

| Scenario | What it does |
|---|---|
| `payments_outage`      | Error storm + 5× latency on `payments` for 30s |
| `catalog_latency`      | 8× p95 latency on `catalog`                    |
| `inventory_deadlock`   | Error burst on `inventory`                     |
| `notifications_flood`  | 5× warn-level flood on `notifications`         |
| `search_index_fail`    | Error burst on `search`                        |

Within seconds the anomaly panel fills, the service graph pulses the
originating node, and downstream services are highlighted with hop distances.

---

## Architecture

```
             ┌────────────────────┐
             │  Synthetic Log     │
             │  Generator         │
             └─────────┬──────────┘
                       │ LogRecord(JSON)
                       ▼
             ┌────────────────────┐
             │  Async Stream Bus  │  (Kafka-shaped API, in-process)
             └─────────┬──────────┘
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
 ┌────────────┐  ┌─────────────┐  ┌──────────────┐
 │  DuckDB    │  │  Drain      │  │  Service     │
 │  Storage   │  │  Template   │  │  Graph       │
 │ (columnar) │  │  Miner      │  │  Builder     │
 └─────┬──────┘  └──────┬──────┘  └──────┬───────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌────────────────────┐
              │  3-layer Anomaly   │  Z-score · IsolationForest · new-template
              │     Detector       │
              └─────────┬──────────┘
                        │ Anomaly + blast_radius
                        ▼
              ┌────────────────────┐
              │  FastAPI + WS hub  │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  React / D3        │
              │  Dashboard         │
              └────────────────────┘
```

### Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Stream bus  | `asyncio.Queue` with Kafka-shaped API | swap for `confluent-kafka` by replacing one file |
| Storage     | **DuckDB**                  | embedded columnar OLAP; same execution model as ClickHouse |
| Detection   | **scikit-learn IsolationForest** + custom Z-score + **Drain** | three complementary paradigms |
| API         | **FastAPI** + WebSockets    | native async, single-digit-ms WS ticks |
| Frontend    | **React · TypeScript · Vite** | strict types, fast HMR |
| Styling     | **Tailwind v3** with a token palette | dark neon theme |
| Viz         | **D3.js**                   | force-layout graph + area/line timeline + bar overlay |

---

## Technical deep-dive

### 1. Log ingestion and storage

The synthetic generator simulates a 12-service e-commerce DAG
(`gateway → auth/catalog/search → cart → checkout → payments → ledger`,
with `recommendations`, `fulfillment`, `notifications`, `analytics` and
`sessions` branching off). Each trace walks the DAG randomly, emitting a
correlated `LogRecord` per service with realistic latency, error
distributions, and parent/child linkage.

Records flow through a tiny Kafka-shaped pub/sub (`stream_bus.py`). Two
independent consumer groups drain the topic — one writes to DuckDB, the
other feeds the Drain template miner. DuckDB is used for its columnar
execution engine: every detection tick runs a handful of
`GROUP BY service` / `QUANTILE_CONT` queries over the full 60-second
window in under a millisecond.

### 2. Three-layer anomaly detection

**Rate detector.** A rolling `RollingStat` keeps the last 60 samples per
service for log volume, error count, and p95 latency. On each tick we
compute a Z-score and fire a `rate_spike` if it crosses `σ ≥ 3` with a
minimum absolute floor (so a quiet service cannot false-positive off two
error lines).

**Feature-based detector.** Every tick we build a per-service feature
matrix `[total, errors, warns, mean_lat, p95_lat, error_rate]`, take
`log1p` to dampen heavy tails, and fit a fresh `IsolationForest` with
`contamination=0.06`. Services the forest flags as outliers receive a
`feature_outlier` anomaly weighted by their decision score.

**Structural detector.** The `Drain` class is a compact ~120-line
implementation of the Drain log parsing algorithm (He et al., ICWS 2017).
Log lines are tokenised, numeric / hex / id tokens are replaced by `<*>`,
and tokens walk a fixed-depth tree to a leaf where the most similar
existing template is either merged or a new one is created. A brand-new
template appearing after the warmup window fires a `new_template`
anomaly.

Anomalies from all three detectors converge into a single deduplicating
queue and are annotated with their blast radius before being broadcast.

### 3. Service graph + blast radius

The service dependency graph is **inferred live from the logs** — no
topology config. Every tick we pull the `(parent_service, service)` pairs
from DuckDB for the current window, bump their edge weights, and decay
the whole graph by `0.92` so the shape reflects *current* behaviour, not
lifetime history.

Blast radius is a **weighted forward BFS** from the anomalous service,
bounded to `max_depth=4` and ignoring edges with normalised weight below
`0.1`. Hop distances become the `+1 / +2 / +3` pill labels in the UI, and
edges whose endpoints are both in the blast set are drawn in red.

### 4. UI rendering

The frontend opens a single WebSocket that receives a coalesced
`StreamMessage` snapshot every ~400ms. The D3 force simulation is
persistent across ticks — node objects are reused so positions remain
stable as the graph mutates. Each new anomaly activates a pulse-ring
animation on the originating node, a glow filter on every downstream
node, and red edge colouring across the blast set. The log feed
highlights lines from the active service in red.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health`                  | health probe |
| `GET`  | `/api/stats`                   | full `StreamMessage` snapshot |
| `GET`  | `/api/scenarios`               | list injectable scenarios |
| `POST` | `/api/scenarios/{name}`        | inject a failure scenario |
| `WS`   | `/ws/stream`                   | live push of `StreamMessage` JSON |

---

## Project layout

```
logflow-anomaly-engine/
├── backend/
│   ├── main.py            FastAPI app, REST routes, WebSocket broadcaster
│   ├── pipeline.py        async orchestrator (generator → bus → storage → detector)
│   ├── generator.py       synthetic 12-service log generator + scenarios
│   ├── stream_bus.py      Kafka-shaped async pub/sub
│   ├── storage.py         DuckDB columnar store + window queries
│   ├── drain.py           Drain log-template miner
│   ├── detector.py        Z-score + IsolationForest + new-template detector
│   ├── graph.py           service graph builder + blast-radius BFS
│   ├── schemas.py         Pydantic wire formats
│   └── config.py          tunables
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── hooks/useLiveStream.ts
│       └── components/
│           ├── Header.tsx
│           ├── KpiBar.tsx
│           ├── ServiceGraph.tsx
│           ├── LogStream.tsx
│           ├── TimelineChart.tsx
│           ├── AnomalyPanel.tsx
│           └── ScenarioControls.tsx
├── docs/dashboard.png
├── run.sh
├── requirements.txt
└── README.md
```

---

## License

MIT.
