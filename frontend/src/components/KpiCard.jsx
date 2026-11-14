import React from 'react';

export default function KpiCard({ title, value, hint, badge, variant = 'cyan', icon: Icon }) {
  const styles = {
    cyan: {
      card: 'border-slate-200 dark:border-cyan-500/20 hover:border-cyan-400 dark:hover:border-cyan-500/40',
      icon: 'text-cyan-600 dark:text-cyan-400 bg-cyan-50 dark:bg-cyan-500/10 border-cyan-200 dark:border-cyan-500/20',
      val: 'text-slate-900 dark:text-white',
    },
    emerald: {
      card: 'border-slate-200 dark:border-emerald-500/20 hover:border-emerald-400 dark:hover:border-emerald-500/40',
      icon: 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20',
      val: 'text-emerald-600 dark:text-emerald-400',
    },
    amber: {
      card: 'border-slate-200 dark:border-amber-500/20 hover:border-amber-400 dark:hover:border-amber-500/40',
      icon: 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20',
      val: 'text-amber-600 dark:text-amber-400',
    },
    rose: {
      card: 'border-slate-200 dark:border-rose-500/20 hover:border-rose-400 dark:hover:border-rose-500/40',
      icon: 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20',
      val: 'text-rose-600 dark:text-rose-400',
    },
    purple: {
      card: 'border-slate-200 dark:border-indigo-500/20 hover:border-indigo-400 dark:hover:border-indigo-500/40',
      icon: 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/20',
      val: 'text-indigo-600 dark:text-indigo-400',
    },
    slate: {
      card: 'border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-700',
      icon: 'text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700',
      val: 'text-slate-900 dark:text-slate-100',
    },
  };

  const current = styles[variant] || styles.cyan;

  return (
    <div
      className={`p-4 rounded-2xl bg-white dark:bg-slate-900/60 border shadow-sm dark:shadow-none transition-all duration-200 hover:-translate-y-0.5 flex flex-col justify-between ${current.card}`}
    >
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 font-sans">
            {title}
          </span>
          {Icon && (
            <div className={`p-1.5 rounded-lg border ${current.icon}`}>
              <Icon className="w-3.5 h-3.5" />
            </div>
          )}
        </div>

        <div className="flex items-baseline gap-2 flex-wrap">
          <span className={`text-2xl font-extrabold tracking-tight font-sans ${current.val}`}>
            {value}
          </span>
          {badge && (
            <span className="text-[10px] font-medium font-sans px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300">
              {badge}
            </span>
          )}
        </div>
      </div>

      {hint && (
        <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-2.5 font-sans pt-2 border-t border-slate-100 dark:border-slate-800/60 truncate" title={hint}>
          {hint}
        </div>
      )}
    </div>
  );
}
