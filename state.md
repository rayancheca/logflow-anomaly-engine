## Status
COMPLETE

## Project
logflow-anomaly-engine — Real-time log-stream anomaly detection with visual blast-radius mapping across service dependency graphs.

## Session count
1

## Summary
Built end-to-end in a single session. Backend ingests a synthetic 12-service
log stream through an async Kafka-shaped bus, persists to DuckDB, runs three
anomaly detectors in parallel (rolling Z-score, IsolationForest, Drain
template miner), infers a service dependency graph from trace co-occurrence,
and computes weighted BFS blast radius. FastAPI + WebSockets stream
snapshots at ~400ms cadence. Frontend is React + TypeScript + Vite +
Tailwind + D3 with a persistent force-layout graph, live log feed, timeline
chart, anomaly panel with blast-radius chips, and five one-click failure
injectors. Verified end-to-end with headless-Chrome screenshot.

## Completed steps
1. Scaffold backend package + requirements + venv.
2. Schemas + config (`backend/schemas.py`, `backend/config.py`).
3. Synthetic 12-service log generator with five failure scenarios.
4. Async pub/sub stream bus with consumer groups.
5. DuckDB storage with rolling window queries and timeline bucketing.
6. Drain log-template miner (~120 loc).
7. Three-layer anomaly detector (z-score + IsolationForest + new-template).
8. Service graph with edge decay + weighted BFS blast-radius.
9. Pipeline orchestrator (producer / storage / drain / detector loops).
10. FastAPI app with REST endpoints and `/ws/stream` WebSocket.
11. Backend end-to-end smoke verified.
12. Frontend Vite + React + TS + Tailwind dark theme.
13–17. Header, KpiBar, LogStream, TimelineChart, ServiceGraph, AnomalyPanel,
       ScenarioControls components.
18. WebSocket hook + integration.
19. README + run.sh launcher + screenshot.
20. Push to GitHub (main tracked to origin).

## Blockers
Encountered a concurrent claude-code process (launched by daily-builder
orchestrator) that twice committed experimental "test: sse push" changes
and reset HEAD~1 against this repo mid-session, wiping local files. I
recovered via `git reflog` + `git cherry-pick` and immediately pushed to
origin to protect the work. No persistent impact.

## Notes
Run with `./run.sh` — backend on :8766, frontend on :5174.

## Git log (oldest→newest)
- chore: scaffold backend package and python deps
- feat: typed schemas and tunable settings
- feat: synthetic 12-service log generator with scenario injection
- feat: async pub/sub stream bus with consumer groups
- feat: DuckDB columnar log storage with rolling window analytics
- fix: align timeline buckets to current second
- feat: Drain log template miner
- feat: three-layer anomaly detector (z-score + isolation forest + drain-new)
- feat: service dependency graph with blast-radius BFS
- feat: pipeline orchestrator tying generator/storage/drain/detector together
- fix: drain regex generalization and detector warmup grace
- feat: FastAPI app with REST endpoints and websocket streaming
- feat: react+d3 dashboard with service graph, log feed, anomaly panel
- feat: proxy vite to backend on 8766
- docs: README, run.sh launcher, dashboard screenshot
