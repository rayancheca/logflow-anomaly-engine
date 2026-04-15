import { useEffect, useMemo, useState } from "react";
import type { Severity, TemplateInfo } from "../types";
import { listTemplates } from "../api";

interface Props {
  services: string[];
}

const LEVELS: (Severity | "*")[] = ["*", "DEBUG", "INFO", "WARN", "ERROR"];

const LEVEL_STYLE: Record<string, string> = {
  DEBUG: "text-slate-500",
  INFO:  "text-signal-cyan",
  WARN:  "text-signal-amber",
  ERROR: "text-signal-red",
  FATAL: "text-signal-red",
};

export default function TemplateExplorer({ services }: Props) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [service, setService] = useState<string>("*");
  const [level, setLevel] = useState<string>("*");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    async function load() {
      setLoading(true);
      try {
        const rows = await listTemplates({
          limit: 60,
          service: service === "*" ? undefined : service,
          level:   level === "*" ? undefined : level,
        });
        if (!cancelled) setTemplates(rows);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    interval = setInterval(load, 4000);
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [service, level]);

  const maxCount = useMemo(
    () => templates.reduce((m, t) => Math.max(m, t.count), 1),
    [templates],
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <div className="panel-title">drain template explorer</div>
        <div className="flex items-center gap-2 text-[10.5px] mono">
          <label className="text-slate-500">service</label>
          <select
            value={service}
            onChange={(e) => setService(e.target.value)}
            className="bg-ink-700/60 border border-white/10 rounded px-2 py-1 text-slate-200 outline-none focus:border-accent-500/50"
          >
            <option value="*">all</option>
            {services.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <label className="text-slate-500 ml-2">level</label>
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            className="bg-ink-700/60 border border-white/10 rounded px-2 py-1 text-slate-200 outline-none focus:border-accent-500/50"
          >
            {LEVELS.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
          {loading && <span className="text-slate-600 ml-1">…</span>}
        </div>
      </div>

      <div className="max-h-[460px] overflow-y-auto scroll-thin divide-y divide-white/5 rounded-lg border border-white/5 bg-ink-800/40">
        {templates.length === 0 && (
          <div className="text-[11px] text-slate-600 mono p-3">no templates match those filters</div>
        )}
        {templates.map((t) => {
          const bar = (t.count / maxCount) * 100;
          return (
            <div key={t.template_id} className="px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="text-[9px] mono px-1 rounded bg-white/5 text-slate-500">
                  #{t.template_id}
                </span>
                <span className="mono text-[10px] text-slate-400 min-w-[78px] truncate">
                  {t.service ?? "?"}
                </span>
                <span className={`mono text-[9px] ${LEVEL_STYLE[t.level ?? "INFO"]}`}>
                  {t.level ?? "INFO"}
                </span>
                <span className="mono text-[11px] text-slate-300 truncate flex-1">
                  {t.template}
                </span>
                <span className="mono text-[10px] text-slate-500 tabular-nums w-10 text-right">
                  {t.count}
                </span>
              </div>
              <div className="mt-1 h-[3px] w-full bg-white/5 rounded overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-accent-500/60 to-accent-400"
                  style={{ width: `${bar}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
