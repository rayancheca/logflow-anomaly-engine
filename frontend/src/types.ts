export type Severity = "DEBUG" | "INFO" | "WARN" | "ERROR" | "FATAL";
export type AnomalyKind = "rate_spike" | "feature_outlier" | "new_template";

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

export interface Anomaly {
  id: string;
  ts: number;
  kind: AnomalyKind;
  service: string;
  severity: number;
  description: string;
  blast_radius: string[];
  blast_hops: Record<string, number>;
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

export interface Kpi {
  logs_per_sec: number;
  error_rate: number;
  active_services: number;
  anomalies_last_min: number;
  templates_tracked: number;
  window_seconds: number;
  uptime_seconds: number;
}

export interface TimelinePoint {
  ts: number;
  total: number;
  errors: number;
  warns: number;
}

export interface StreamMessage {
  kind: "tick";
  kpi: Kpi;
  logs: LogRecord[];
  anomalies: Anomaly[];
  graph: ServiceGraphSnapshot;
  timeline: TimelinePoint[];
}
