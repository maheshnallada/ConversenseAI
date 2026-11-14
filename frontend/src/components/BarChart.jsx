import React from 'react';

export default function BarChart({ title, data = {}, variant = 'cyan' }) {
  const entries = Object.entries(data);
  const total = entries.reduce((acc, [, val]) => acc + val, 0) || 1;

  const barColor = {
    cyan: 'bg-brand-cyan',
    emerald: 'bg-brand-emerald',
    amber: 'bg-brand-amber',
    rose: 'bg-brand-rose',
    purple: 'bg-indigo-400',
  }[variant] || 'bg-brand-cyan';

  return (
    <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 glass-card">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 mb-4">{title}</h3>
      {entries.length === 0 ? (
        <div className="text-xs text-slate-500 py-6 text-center">No telemetry recorded yet</div>
      ) : (
        <div className="space-y-3.5">
          {entries.map(([label, count]) => {
            const pct = ((count / total) * 100).toFixed(1);
            return (
              <div key={label} className="space-y-1">
                <div className="flex justify-between text-xs font-medium">
                  <span className="text-slate-300">{label}</span>
                  <span className="text-slate-400 font-mono">
                    {count} <span className="text-slate-500 font-mono">({pct}%)</span>
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800/80 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

