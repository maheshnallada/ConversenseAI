import React from 'react';

export default function BarChart({ title, data = {}, variant = 'cyan' }) {
  const entries = Object.entries(data);
  const total = entries.reduce((acc, [, val]) => acc + val, 0) || 1;

  const barColor = {
    cyan: 'bg-cyan-500',
    emerald: 'bg-emerald-500',
    amber: 'bg-amber-500',
    rose: 'bg-rose-500',
    purple: 'bg-indigo-500',
  }[variant] || 'bg-cyan-500';

  return (
    <div className="p-4 sm:p-5 rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none transition-all">
      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-4">
        {title}
      </h3>
      {entries.length === 0 ? (
        <div className="text-xs text-slate-400 dark:text-slate-500 py-6 text-center">
          No telemetry recorded yet
        </div>
      ) : (
        <div className="space-y-3.5">
          {entries.map(([label, count]) => {
            const pct = ((count / total) * 100).toFixed(1);
            return (
              <div key={label} className="space-y-1">
                <div className="flex justify-between text-xs font-medium">
                  <span className="text-slate-700 dark:text-slate-300 truncate max-w-[200px]">
                    {label}
                  </span>
                  <span className="text-slate-500 dark:text-slate-400 font-mono text-[11px]">
                    {count} <span className="text-slate-400 dark:text-slate-500">({pct}%)</span>
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
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
