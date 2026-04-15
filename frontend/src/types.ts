export type Severity = "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL";
export type AnomalyKind = "rate_spike" | "feature_outlier" | "new_template" | "rule_fired";
export type IncidentState = "active" | "resolving" | "resolved";
export type RuleMetric = "error_rate" | "p95_latency" | "logs_per_min";
export type RuleOp = ">" | "<" | ">=" | "<=";

export interface LogRecord {
  ts: number;
  service: string;
  level: Severity;
  trace_id: string;
  span_id: string;
  parent_service: string | null;
  latency_ms: number;
  status_code: number;
  message: string;
  template_id: number | null;
}

export interface TraceSpan {
  ts: number;
  service: string;
  parent_service: string | null;
  level: Severity;
  latency_ms: number;
  status_code: number;
  message: string;
  span_id: string;
  depth: number;
}

export interface Trace {
  trace_id: string;
  started: number;
  duration_ms: number;
  services: string[];
  has_errors: boolean;
  spans: TraceSpan[];
}

export interface Anomaly {
  id: string;
  ts: number;
  kind: AnomalyKind;
  service: string;
  severity: number;
  description: string;
  blast_radius: string[];
  blast_hops: Record<string, number>;
  incident_id: string | null;
}

export interface Incident {
  id: string;
  started: number;
  last_ts: number;
  state: IncidentState;
  severity: number;
  root_service: string;
  suspected_cause: string;
  services: string[];
  impact: string[];
  impact_hops: Record<string, number>;
  anomaly_ids: string[];
  anomaly_kinds: AnomalyKind[];
  title: string;
  anomaly_count: number;
}

export interface AlertRule {
  id: string;
  name: string;
  service: string;
  metric: RuleMetric;
  op: RuleOp;
  threshold: number;
  duration_s: number;
  enabled: boolean;
  fired_count: number;
  last_fired: number | null;
}

export interface ServiceNode {
  id: string;
  group: string;
  logs_per_min: number;
  error_rate: number;
  mean_latency_ms: number;
  health: number;
}

export interface ServiceEdge {
  source: string;
  target: string;
  weight: number;
}

export interface ServiceGraphSnapshot {
  nodes: ServiceNode[];
  edges: ServiceEdge[];
}

export interface ServiceLatencyPoint {
  ts: number;
  p50: number;
  p95: number;
  p99: number;
  mean: number;
}

export interface TemplateInfo {
  template_id: number;
  template: string;
  count: number;
  service: string | null;
  level: Severity | null;
  first_seen: number | null;
  last_seen: number | null;
}

export interface ServiceDetail {
  id: string;
  group: string;
  logs_per_min: number;
  error_rate: number;
  mean_latency_ms: number;
  p95_latency_ms: number;
  health: number;
  upstream: ServiceEdge[];
  downstream: ServiceEdge[];
  latency_series: ServiceLatencyPoint[];
  top_templates: TemplateInfo[];
  recent_errors: LogRecord[];
  forecast_error_rate: number;
  forecast_stddev: number;
}

export interface Kpi {
  logs_per_sec: number;
  error_rate: number;
  active_services: number;
  anomalies_last_min: number;
  templates_tracked: number;
  active_incidents: number;
  window_seconds: number;
  uptime_seconds: number;
}

export interface TimelinePoint {
  ts: number;
  total: number;
  errors: number;
  warns: number;
}

export interface SearchHit {
  ts: number;
  service: string;
  level: Severity;
  message: string;
  trace_id: string;
  latency_ms: number;
}

export interface SearchResult {
  query: string;
  hits: SearchHit[];
  total_scanned: number;
  window_seconds: number;
}

export interface CorrelationMatrix {
  services: string[];
  matrix: number[][];
  window_seconds: number;
  ts: number;
}

export interface StreamMessage {
  kind: "tick";
  kpi: Kpi;
  logs: LogRecord[];
  anomalies: Anomaly[];
  incidents: Incident[];
  graph: ServiceGraphSnapshot;
  timeline: TimelinePoint[];
  rules: AlertRule[];
  active_scenarios: string[];
}
