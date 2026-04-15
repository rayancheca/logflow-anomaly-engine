import type {
  AlertRule,
  CorrelationMatrix,
  Incident,
  RuleMetric,
  RuleOp,
  SearchResult,
  ServiceDetail,
  TemplateInfo,
  Trace,
} from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`http ${res.status}`);
  return (await res.json()) as T;
}

export async function listScenarios(): Promise<{ scenarios: string[]; active: string[] }> {
  const res = await fetch("/api/scenarios");
  if (!res.ok) return { scenarios: [], active: [] };
  return res.json();
}

export async function triggerScenario(name: string): Promise<boolean> {
  const res = await fetch(`/api/scenarios/${name}`, { method: "POST" });
  if (!res.ok) return false;
  const d = (await res.json()) as { ok: boolean };
  return d.ok;
}

export async function getServiceDetail(name: string): Promise<ServiceDetail | null> {
  const res = await fetch(`/api/service/${encodeURIComponent(name)}`);
  if (res.status === 404) return null;
  return json<ServiceDetail>(res);
}

export async function getTrace(traceId: string): Promise<Trace | null> {
  const res = await fetch(`/api/trace/${encodeURIComponent(traceId)}`);
  if (res.status === 404) return null;
  return json<Trace>(res);
}

export async function listTemplates(params: {
  limit?: number; service?: string; level?: string;
} = {}): Promise<TemplateInfo[]> {
  const q = new URLSearchParams();
  if (params.limit)   q.set("limit", String(params.limit));
  if (params.service) q.set("service", params.service);
  if (params.level)   q.set("level", params.level);
  const res = await fetch(`/api/templates?${q.toString()}`);
  return json<TemplateInfo[]>(res);
}

export async function searchLogs(params: {
  q: string; service?: string; level?: string; limit?: number;
}): Promise<SearchResult> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.service) qs.set("service", params.service);
  if (params.level)   qs.set("level", params.level);
  if (params.limit)   qs.set("limit", String(params.limit));
  const res = await fetch(`/api/search?${qs.toString()}`);
  return json<SearchResult>(res);
}

export async function getCorrelations(): Promise<CorrelationMatrix> {
  return json<CorrelationMatrix>(await fetch("/api/correlations"));
}

export async function listRules(): Promise<AlertRule[]> {
  return json<AlertRule[]>(await fetch("/api/rules"));
}

export interface RuleCreateInput {
  name: string;
  service: string;
  metric: RuleMetric;
  op: RuleOp;
  threshold: number;
  duration_s: number;
}

export async function addRule(body: RuleCreateInput): Promise<AlertRule> {
  const res = await fetch("/api/rules", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<AlertRule>(res);
}

export async function deleteRule(id: string): Promise<boolean> {
  const res = await fetch(`/api/rules/${id}`, { method: "DELETE" });
  if (!res.ok) return false;
  const d = (await res.json()) as { ok: boolean };
  return d.ok;
}

export async function toggleRule(id: string, enabled: boolean): Promise<AlertRule | null> {
  const res = await fetch(`/api/rules/${id}/toggle?enabled=${enabled}`, { method: "POST" });
  if (!res.ok) return null;
  return json<AlertRule>(res);
}

export async function listIncidents(): Promise<Incident[]> {
  return json<Incident[]>(await fetch("/api/incidents"));
}

export async function recentTraces(errorsOnly = false, limit = 30): Promise<string[]> {
  const q = new URLSearchParams();
  q.set("limit", String(limit));
  if (errorsOnly) q.set("errors_only", "true");
  const res = await fetch(`/api/traces/recent?${q.toString()}`);
  const d = (await res.json()) as { trace_ids: string[] };
  return d.trace_ids;
}
