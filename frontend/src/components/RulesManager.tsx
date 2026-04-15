import { useState } from "react";
import type { AlertRule, RuleMetric, RuleOp } from "../types";
import { addRule, deleteRule, toggleRule } from "../api";

interface Props {
  rules: AlertRule[];
  services: string[];
  onChanged: () => void;
}

const METRICS: { key: RuleMetric; label: string }[] = [
  { key: "error_rate",   label: "error rate" },
  { key: "p95_latency",  label: "p95 latency" },
  { key: "logs_per_min", label: "logs/min" },
];

const OPS: RuleOp[] = [">", "<", ">=", "<="];

function fmtThreshold(metric: RuleMetric, v: number): string {
  if (metric === "error_rate") return `${(v * 100).toFixed(1)}%`;
  if (metric === "p95_latency") return `${v.toFixed(0)}ms`;
  return `${v.toFixed(0)}/min`;
}

export default function RulesManager({ rules, services, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    service: "*",
    metric: "error_rate" as RuleMetric,
    op: ">" as RuleOp,
    threshold: 0.05,
    duration_s: 5,
  });
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!form.name.trim()) return;
    setBusy(true);
    try {
      await addRule(form);
      setForm({ ...form, name: "", threshold: 0.05 });
      setOpen(false);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: string) {
    await deleteRule(id);
    onChanged();
  }

  async function onToggle(rule: AlertRule) {
    await toggleRule(rule.id, !rule.enabled);
    onChanged();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="panel-title">alert rules · {rules.length}</div>
        <button
          onClick={() => setOpen(!open)}
          className="text-[10px] mono px-2 py-1 rounded border border-white/10 bg-ink-700/50 text-slate-300 hover:bg-ink-700 hover:border-white/20 transition"
        >
          {open ? "× close" : "+ new rule"}
        </button>
      </div>

      {open && (
        <div className="mb-3 p-3 rounded-lg border border-accent-500/30 bg-accent-500/5 space-y-2">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="rule name · e.g. payments error > 5%"
            className="w-full bg-ink-700/60 border border-white/10 rounded px-2 py-1.5 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
          />
          <div className="grid grid-cols-4 gap-2">
            <select
              value={form.service}
              onChange={(e) => setForm({ ...form, service: e.target.value })}
              className="bg-ink-700/60 border border-white/10 rounded px-2 py-1.5 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
            >
              <option value="*">any service</option>
              {services.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select
              value={form.metric}
              onChange={(e) => setForm({ ...form, metric: e.target.value as RuleMetric })}
              className="bg-ink-700/60 border border-white/10 rounded px-2 py-1.5 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
            >
              {METRICS.map((m) => (
                <option key={m.key} value={m.key}>{m.label}</option>
              ))}
            </select>
            <select
              value={form.op}
              onChange={(e) => setForm({ ...form, op: e.target.value as RuleOp })}
              className="bg-ink-700/60 border border-white/10 rounded px-2 py-1.5 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
            >
              {OPS.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
            <input
              type="number"
              step="0.01"
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
              className="bg-ink-700/60 border border-white/10 rounded px-2 py-1.5 text-[11px] mono text-slate-200 outline-none focus:border-accent-500/50"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[10px] mono text-slate-500">dwell</label>
            <input
              type="number"
              value={form.duration_s}
              onChange={(e) => setForm({ ...form, duration_s: Number(e.target.value) })}
              className="w-16 bg-ink-700/60 border border-white/10 rounded px-2 py-1 text-[11px] mono text-slate-200 outline-none"
            />
            <span className="text-[10px] mono text-slate-500">seconds</span>
            <button
              disabled={busy || !form.name.trim()}
              onClick={submit}
              className="ml-auto text-[11px] mono px-3 py-1 rounded bg-accent-500/20 text-accent-400 border border-accent-500/40 hover:bg-accent-500/30 disabled:opacity-40"
            >
              add rule
            </button>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-white/5 divide-y divide-white/5 bg-ink-800/40 max-h-[340px] overflow-y-auto scroll-thin">
        {rules.length === 0 && (
          <div className="text-[11px] text-slate-600 mono p-3">no rules defined</div>
        )}
        {rules.map((r) => (
          <div key={r.id} className="flex items-center gap-3 px-3 py-2">
            <button
              onClick={() => onToggle(r)}
              className={`w-8 h-[18px] rounded-full transition relative ${
                r.enabled ? "bg-accent-500/60" : "bg-slate-700"
              }`}
            >
              <span
                className={`absolute top-[2px] left-[2px] w-[14px] h-[14px] bg-slate-100 rounded-full transition ${
                  r.enabled ? "translate-x-[14px]" : ""
                }`}
              />
            </button>
            <div className="min-w-0 flex-1">
              <div className="mono text-[11.5px] text-slate-100 truncate">{r.name}</div>
              <div className="mono text-[10px] text-slate-500 mt-0.5 truncate">
                {r.service} · {r.metric} {r.op} {fmtThreshold(r.metric, r.threshold)} · {r.duration_s}s dwell
              </div>
            </div>
            <div className="mono text-[10px] text-slate-500 text-right shrink-0">
              <div>fired {r.fired_count}</div>
              <div className="text-slate-600">
                {r.last_fired ? new Date(r.last_fired * 1000).toISOString().slice(11, 19) : "—"}
              </div>
            </div>
            <button
              onClick={() => onDelete(r.id)}
              className="text-slate-600 hover:text-signal-red text-sm shrink-0"
              aria-label="delete"
              title="delete rule"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
