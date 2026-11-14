import React from 'react';

export default function KpiCard({ title, value, hint, badge, variant = 'cyan', icon: Icon }) {
  const accentColors = {
    cyan: 'border-cyan-500/20 from-cyan-500/10 text-brand-cyan',
    emerald: 'border-emerald-500/20 from-emerald-500/10 text-brand-emerald',
    amber: 'border-amber-500/20 from-amber-500/10 text-brand-amber',
    rose: 'border-rose-500/20 from-rose-500/10 text-brand-rose',
    purple: 'border-indigo-500/20 from-indigo-500/10 text-indigo-400',
    slate: 'border-slate-700/40 from-slate-800/10 text-slate-300',
  };

  const currentAccent = accentColors[variant] || accentColors.cyan;

  return (
    <div className={`relative p-5 rounded-2xl bg-gradient-to-b ${currentAccent} to-slate-900/60 border ${currentAccent.split(' ')[0]} glass-card transition-all hover:scale-[1.01] hover:border-slate-700`}>
      <div className="flex items-center justify-between text-slate-400 mb-2">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{title}</span>
        {Icon && <Icon className={`w-4 h-4 ${currentAccent.split(' ').pop()}`} />}
      </div>
      <div className="text-2xl font-bold font-mono tracking-tight text-slate-100 flex items-baseline gap-2">
        <span>{value}</span>
        {badge && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
            {badge}
          </span>
        )}
      </div>
      {hint && <div className="text-xs text-slate-400 mt-2 font-mono">{hint}</div>}
    </div>
  );
}

