import React from 'react';
import { RefreshCw, UploadCloud, Radio } from 'lucide-react';

const TITLES = {
  overview: {
    title: 'Platform Observability Overview',
    subtitle: 'Unified telephony metrics, timeline playback reconciliation, and multi-dimensional evaluation scorecard.',
  },
  interactions: {
    title: 'Interactions Explorer',
    subtitle: 'Filter, inspect, and evaluate conversations across latency, quality scorecard, and customer sentiment.',
  },
  drilldown: {
    title: 'Call Drill-Down & Audio Playback',
    subtitle: 'Stereo playback, synchronized turns timeline with reconciliation tags, and human adjudication audit trail.',
  },
  ingest: {
    title: 'On-Demand Data Ingestion & Evaluation',
    subtitle: 'Ingest call archives (ZIP) or server paths to trigger full turn extraction, timeline reconstruction, and evaluation.',
  },
  benchmark: {
    title: 'Golden Dataset Benchmark Validation',
    subtitle: 'Evaluate automated compliance and outcome decisions against human ground-truth labels across all calls.',
  },
  evaluators: {
    title: 'Evaluators & Model Gateway Configuration',
    subtitle: 'Active never-rule compliance safety policies, LLM rate cards, and dynamic model routing.',
  },
};

export default function Topbar({ activeTab, onRefresh, onIngestClick, isRefreshing }) {
  const current = TITLES[activeTab] || TITLES.overview;

  return (
    <header className="h-16 px-8 border-b border-slate-800/80 bg-[#090d16]/80 backdrop-blur-md flex items-center justify-between sticky top-0 z-20">
      <div>
        <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
          {current.title}
        </h2>
        <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{current.subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        {activeTab !== 'ingest' && (
          <button
            onClick={onIngestClick}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-brand-cyan border border-cyan-500/30 text-xs font-medium transition-all"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Ingest Call</span>
          </button>
        )}

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 text-xs font-medium border border-slate-700/60 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-brand-cyan' : ''}`} />
          <span>Refresh</span>
        </button>

        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-500/20 text-[11px] font-mono text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>SYSTEM READY</span>
        </div>
      </div>
    </header>
  );
}

