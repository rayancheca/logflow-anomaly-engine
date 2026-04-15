interface Props {
  connected: boolean;
  uptime: number;
}

export default function Header({ connected, uptime }: Props) {
  const mins = Math.floor(uptime / 60);
  const secs = Math.floor(uptime % 60);
  return (
    <header className="border-b border-white/5 bg-ink-900/70 backdrop-blur-sm sticky top-0 z-20">
      <div className="max-w-[1600px] mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-9 h-9 rounded-lg bg-gradient-to-br from-accent-500/30 to-signal-violet/30 border border-accent-500/40 shadow-glow">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent-400">
              <path d="M3 12h4l3-9 4 18 3-9h4" />
            </svg>
          </div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight">
              LogFlow <span className="text-slate-400 font-normal">· Anomaly Engine</span>
            </div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
              real-time log stream · blast-radius mapping
            </div>
          </div>
        </div>
        <div className="flex items-center gap-5 text-[11px] mono">
          <div className="flex items-center gap-2 text-slate-400">
            <span className="w-1.5 h-1.5 rounded-full bg-signal-cyan animate-pulse" />
            window 60s
          </div>
          <div className="text-slate-400">
            uptime <span className="text-slate-200">{mins}m {secs}s</span>
          </div>
          <div className={`flex items-center gap-2 ${connected ? "text-signal-green" : "text-signal-red"}`}>
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-signal-green" : "bg-signal-red"}`} />
            {connected ? "LIVE" : "OFFLINE"}
          </div>
        </div>
      </div>
    </header>
  );
}
