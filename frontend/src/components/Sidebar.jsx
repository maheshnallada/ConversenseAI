import React from 'react';
import {
  BarChart3,
  PhoneCall,
  Search,
  UploadCloud,
  Award,
  Sliders,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Radio
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: 'Platform Overview', icon: BarChart3 },
  { id: 'interactions', label: 'Interactions Explorer', icon: PhoneCall },
  { id: 'drilldown', label: 'Call Drill-Down', icon: Search },
  { id: 'ingest', label: 'Ingest & Evaluate', icon: UploadCloud },
  { id: 'benchmark', label: 'Golden Benchmark', icon: Award },
  { id: 'evaluators', label: 'Evaluators & Config', icon: Sliders },
];

export default function Sidebar({
  activeTab,
  onTabChange,
  isOpen = false,
  onClose,
  isCollapsed = false,
  onToggleCollapse,
}) {
  const handleItemClick = (id) => {
    onTabChange(id);
    if (onClose) onClose();
  };

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm lg:hidden transition-opacity duration-200"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 bg-white dark:bg-[#080d18] border-r border-slate-200 dark:border-slate-800/80 flex flex-col flex-shrink-0 transition-all duration-200 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full lg:translate-x-0'
        } ${isCollapsed ? 'lg:w-[72px]' : 'lg:w-64'}`}
      >
        {/* Brand Header */}
        <div className={`p-4 flex items-center border-b border-slate-200 dark:border-slate-800/80 ${isCollapsed ? 'justify-center' : 'justify-between'}`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center font-bold text-white text-base shadow-sm shrink-0">
              CA
            </div>
            {!isCollapsed && (
              <div className="overflow-hidden">
                <div className="flex items-center gap-1.5">
                  <h1 className="font-bold text-slate-900 dark:text-slate-100 text-sm tracking-tight truncate">
                    Conversense
                  </h1>
                  <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-cyan-100 dark:bg-cyan-950/80 border border-cyan-200 dark:border-cyan-500/30 text-cyan-700 dark:text-cyan-400">
                    AI
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Voice Observability</p>
              </div>
            )}
          </div>

          {/* Mobile Close Button */}
          {onClose && (
            <button
              onClick={onClose}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Navigation Menu */}
        <nav className="p-2.5 space-y-1 flex-1 overflow-y-auto overflow-x-hidden">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                title={isCollapsed ? item.label : undefined}
                className={`w-full flex items-center rounded-xl text-xs font-medium transition-all duration-150 ${
                  isCollapsed
                    ? 'justify-center p-3'
                    : 'gap-3 px-3.5 py-2.5'
                } ${
                  isActive
                    ? 'bg-cyan-50 text-cyan-800 border border-cyan-200 shadow-sm dark:bg-slate-800/90 dark:text-cyan-400 dark:border-cyan-500/30 font-semibold'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/40'
                }`}
              >
                <Icon
                  className={`w-4 h-4 shrink-0 ${
                    isActive ? 'text-cyan-600 dark:text-cyan-400' : 'text-slate-400 dark:text-slate-500'
                  }`}
                />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
                {!isCollapsed && item.id === 'ingest' && (
                  <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 dark:bg-emerald-950/80 dark:border-emerald-500/30 dark:text-emerald-400 font-semibold">
                    NEW
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Campaign Info (Only when expanded) */}
        {!isCollapsed && (
          <div className="p-3.5 m-2.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800/80 text-xs">
            <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 mb-1">
              <span className="uppercase text-[10px] tracking-wider font-semibold">Active Campaign</span>
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            </div>
            <div className="font-semibold text-slate-800 dark:text-slate-200 truncate">
              Health Insurance Outbound
            </div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
              Policy Review Campaign
            </div>
          </div>
        )}

        {/* Collapse Toggle Button at the bottom (Desktop only) */}
        {onToggleCollapse && (
          <div className="p-2 border-t border-slate-200 dark:border-slate-800/80 hidden lg:block">
            <button
              onClick={onToggleCollapse}
              className={`w-full flex items-center rounded-xl text-xs text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors font-medium ${
                isCollapsed ? 'justify-center p-2.5' : 'gap-2 px-3 py-2'
              }`}
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isCollapsed ? (
                <ChevronRight className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              ) : (
                <>
                  <ChevronLeft className="w-4 h-4 text-slate-400" />
                  <span>Collapse Sidebar</span>
                </>
              )}
            </button>
          </div>
        )}
      </aside>
    </>
  );
}
