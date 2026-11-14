import React from 'react';
import {
  BarChart3,
  PhoneCall,
  Search,
  UploadCloud,
  Award,
  Sliders,
  ShieldCheck,
  Activity,
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: 'Platform Overview', icon: BarChart3 },
  { id: 'interactions', label: 'Interactions Explorer', icon: PhoneCall },
  { id: 'drilldown', label: 'Call Drill-Down', icon: Search },
  { id: 'ingest', label: 'Ingest & Evaluate', icon: UploadCloud },
  { id: 'benchmark', label: 'Golden Benchmark', icon: Award },
  { id: 'evaluators', label: 'Evaluators & Config', icon: Sliders },
];

export default function Sidebar({ activeTab, onTabChange }) {
  return (
    <aside className="w-64 bg-[#080d18] border-r border-slate-800/80 flex flex-col flex-shrink-0 min-h-screen">
      {/* Brand Header */}
      <div className="p-5 flex items-center gap-3 border-b border-slate-800/80">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-cyan via-brand-blue to-brand-indigo flex items-center justify-center font-bold text-slate-950 text-lg shadow-lg shadow-cyan-500/20">
          CA
        </div>
        <div>
          <div className="flex items-center gap-1.5">
            <h1 className="font-semibold text-slate-100 text-sm tracking-tight">Conversense</h1>
            <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/30 text-brand-cyan">AI</span>
          </div>
          <p className="text-[11px] text-slate-400 font-mono">Voice Observability</p>
        </div>
      </div>

      {/* Navigation Menu */}
      <nav className="p-3 space-y-1 flex-1">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-slate-800/90 text-brand-cyan border border-cyan-500/30 shadow-sm shadow-cyan-950'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-brand-cyan' : 'text-slate-500'}`} />
              <span>{item.label}</span>
              {item.id === 'ingest' && (
                <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-500/30 text-brand-emerald font-mono">
                  NEW
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Campaign Metadata Footer */}
      <div className="p-4 m-3 rounded-xl bg-slate-900/60 border border-slate-800/80 text-xs">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="uppercase text-[10px] tracking-wider font-semibold">Active Campaign</span>
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
        </div>
        <div className="font-medium text-slate-200 truncate">Health Insurance Outbound</div>
        <div className="text-[11px] text-slate-400 font-mono mt-0.5">Policy Review Campaign</div>
      </div>
    </aside>
  );
}

