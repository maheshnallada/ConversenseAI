import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Search, ChevronLeft, ChevronRight, Eye } from 'lucide-react';

export default function InteractionsView({ onInspectCall }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [outcome, setOutcome] = useState('');
  const [quality, setQuality] = useState('');
  const [status, setStatus] = useState('');

  useEffect(() => {
    loadInteractions(page);
  }, [page, outcome, quality, status]);

  async function loadInteractions(p = 1) {
    setLoading(true);
    try {
      const params = { page: p, page_size: 10 };
      if (search) params.search = search;
      if (outcome) params.outcome = outcome;
      if (quality) params.quality = quality;
      if (status) params.status = status;

      const data = await api.getInteractionsPage(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
      setPage(data.page || 1);
    } catch (e) {
      console.error('Failed to load interactions:', e);
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e) {
    e.preventDefault();
    loadInteractions(1);
  }

  const getQualityBadge = (q) => {
    if (q === 'Good') {
      return 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-400 dark:border-emerald-500/30';
    }
    if (q === 'OK') {
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/80 dark:text-amber-400 dark:border-amber-500/30';
    }
    return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/80 dark:text-rose-400 dark:border-rose-500/30';
  };

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="p-4 rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none flex flex-wrap gap-4 items-center justify-between transition-colors">
        <form onSubmit={handleSearchSubmit} className="relative min-w-[240px] flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search interaction ID or call alias..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-900 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-cyan-500 transition-colors font-mono"
          />
        </form>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300 focus:outline-none focus:border-cyan-500 font-sans"
          >
            <option value="">All Outcomes</option>
            <option value="Not interested">Not interested</option>
            <option value="Callback Requested">Callback Requested</option>
            <option value="Expert Call Booked">Expert Call Booked</option>
            <option value="Call later">Call later</option>
            <option value="Do not call">Do not call</option>
            <option value="Voicemail">Voicemail</option>
          </select>

          <select
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300 focus:outline-none focus:border-cyan-500 font-sans"
          >
            <option value="">All Quality</option>
            <option value="Good">Good</option>
            <option value="OK">OK</option>
            <option value="Bad">Bad</option>
          </select>

          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300 focus:outline-none focus:border-cyan-500 font-sans"
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="abandoned">Abandoned</option>
          </select>
        </div>
      </div>

      {/* Responsive Table Container */}
      <div className="rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none overflow-hidden transition-colors">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs min-w-[700px]">
            <thead className="bg-slate-50 dark:bg-slate-950/60 border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 font-mono uppercase tracking-wider text-[10px]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">Interaction / Call</th>
                <th className="py-3.5 px-4 font-semibold">Start Time</th>
                <th className="py-3.5 px-4 font-semibold">Audio / Telephony</th>
                <th className="py-3.5 px-4 font-semibold">Turns</th>
                <th className="py-3.5 px-4 font-semibold">Outcome Intent</th>
                <th className="py-3.5 px-4 font-semibold">Quality</th>
                <th className="py-3.5 px-4 font-semibold">Sentiment</th>
                <th className="py-3.5 px-4 font-semibold">Cost (USD)</th>
                <th className="py-3.5 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 font-sans">
              {loading ? (
                <tr>
                  <td colSpan="9" className="py-12 text-center text-slate-500 dark:text-slate-400">
                    <div className="inline-block w-6 h-6 rounded-full border-2 border-cyan-500/20 border-t-cyan-500 animate-spin mb-2"></div>
                    <div>Loading call interactions...</div>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan="9" className="py-12 text-center text-slate-400 dark:text-slate-500">
                    No interactions match the selected filters.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.interaction_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-900 dark:text-slate-100">
                        {item.folder_name || 'Call'}
                      </div>
                      <div className="font-mono text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[140px]" title={item.interaction_id}>
                        {item.interaction_id}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                      {item.started_at ? new Date(item.started_at).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                      <span>{item.duration_s?.toFixed(1) || 0}s</span>
                      <span className="text-slate-400 dark:text-slate-500 text-[10px] ml-1">
                        / {item.telephony_duration_s?.toFixed(1) || 0}s
                      </span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-800 dark:text-slate-200">
                      {item.turns_count || 0}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="text-slate-800 dark:text-slate-200 font-medium">
                        {item.outcome || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-mono border ${getQualityBadge(item.quality)}`}>
                        {item.quality || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300 capitalize">
                      {item.sentiment || 'Neutral'}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-amber-600 dark:text-amber-400 font-medium">
                      ${item.cost_usd ? item.cost_usd.toFixed(4) : '0.0000'}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => onInspectCall(item.interaction_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cyan-50 hover:bg-cyan-100 text-cyan-700 border border-cyan-200 dark:bg-cyan-500/10 dark:hover:bg-cyan-500/20 dark:text-cyan-400 dark:border-cyan-500/30 text-xs font-semibold transition-all shadow-sm"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Inspect</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
          <div className="text-slate-500 dark:text-slate-400 font-mono">
            Showing <strong className="text-slate-800 dark:text-slate-200">{items.length}</strong> of{' '}
            <strong className="text-slate-800 dark:text-slate-200">{total}</strong> interactions
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-40 transition-colors shadow-sm"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="font-mono text-slate-700 dark:text-slate-300 px-2">
              Page {page} of {pages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(pages, p + 1))}
              disabled={page >= pages}
              className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-40 transition-colors shadow-sm"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
