import React from 'react';
import { RefreshCw, UploadCloud, Menu, Sun, Moon } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

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

export default function Topbar({
  activeTab,
  onRefresh,
  onIngestClick,
  onToggleMobileMenu,
  isRefreshing,
}) {
  const { isDark, toggleTheme } = useTheme();
  const current = TITLES[activeTab] || TITLES.overview;

  return (
    <header className="h-16 px-4 sm:px-6 lg:px-8 border-b border-slate-200 dark:border-slate-800/80 bg-white/80 dark:bg-[#090d16]/80 backdrop-blur-md flex items-center justify-between sticky top-0 z-30 transition-colors duration-150">
      {/* Left: Mobile Menu Trigger + Titles */}
      <div className="flex items-center gap-3">
        {onToggleMobileMenu && (
          <button
            onClick={onToggleMobileMenu}
            className="lg:hidden p-2 rounded-xl text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Toggle Menu"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        <div>
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2 truncate max-w-[200px] sm:max-w-md">
            {current.title}
          </h2>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 hidden sm:line-clamp-1">
            {current.subtitle}
          </p>
        </div>
      </div>

      {/* Right: Actions & Theme Toggle */}
      <div className="flex items-center gap-2 sm:gap-3">
        {activeTab !== 'ingest' && (
          <button
            onClick={onIngestClick}
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 hover:bg-cyan-100 dark:hover:bg-cyan-500/20 text-cyan-700 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-500/30 text-xs font-semibold transition-all shadow-sm"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Ingest Call</span>
          </button>
        )}

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700/80 text-slate-700 dark:text-slate-300 text-xs font-medium border border-slate-200 dark:border-slate-700/60 transition-all disabled:opacity-50"
          title="Refresh Data"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-cyan-500' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>

        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700/60 transition-colors"
          title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDark ? (
            <Sun className="w-4 h-4 text-amber-400 hover:rotate-45 transition-transform" />
          ) : (
            <Moon className="w-4 h-4 text-slate-700 hover:-rotate-12 transition-transform" />
          )}
        </button>

        {/* System Status Pill */}
        <div className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-500/20 text-[11px] font-mono text-emerald-700 dark:text-emerald-400 font-semibold">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>READY</span>
        </div>
      </div>
    </header>
  );
}
