import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Search, ChevronLeft, ChevronRight, Eye, PhoneForwarded } from 'lucide-react';

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
    if (q === 'Good') return 'bg-emerald-950/80 text-emerald-400 border-emerald-500/30';
    if (q === 'OK') return 'bg-amber-950/80 text-amber-400 border-amber-500/30';
    return 'bg-rose-950/80 text-rose-400 border-rose-500/30';
  };

  const getComplianceBadge = (c) => {
    if (c === 'PASSED') return 'bg-emerald-950/80 text-emerald-400 border-emerald-500/30';
    return 'bg-rose-950/80 text-rose-400 border-rose-500/30';
  };

  return (
    <div className="space-y-4">
      {/* Controls Bar */}
      <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 glass-card flex flex-wrap gap-4 items-center justify-between">
        <form onSubmit={handleSearchSubmit} className="relative min-w-[260px] flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search interaction ID or call alias..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-brand-cyan/50"
          />
        </form>

        <div className="flex items-center gap-3">
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-brand-cyan/50"
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
            className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-brand-cyan/50"
          >
            <option value="">All Quality</option>
            <option value="Good">Good</option>
            <option value="OK">OK</option>
            <option value="Bad">Bad</option>
          </select>

          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-brand-cyan/50"
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="abandoned">Abandoned</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-2xl bg-slate-900/60 border border-slate-800/80 glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-mono uppercase tracking-wider text-[10px]">
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
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {loading ? (
                <tr>
                  <td colSpan="9" className="py-12 text-center text-slate-400">
                    <div className="inline-block w-6 h-6 rounded-full border-2 border-brand-cyan/20 border-t-brand-cyan animate-spin mb-2"></div>
                    <div>Loading call interactions...</div>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan="9" className="py-12 text-center text-slate-500">
                    No interactions match the selected filters.
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.interaction_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-200">{item.folder_name || 'Call'}</div>
                      <div className="font-mono text-[11px] text-slate-400 truncate max-w-[140px]" title={item.interaction_id}>
                        {item.interaction_id}
                      </div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-300">
                      {item.started_at ? new Date(item.started_at).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-300">
                      <span>{item.duration_s?.toFixed(1) || 0}s</span>
                      <span className="text-slate-500 text-[10px] ml-1">/ {item.telephony_duration_s?.toFixed(1) || 0}s</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-200">
                      {item.turns_count || 0}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="text-slate-200 font-medium">{item.outcome || 'N/A'}</span>
                    </td>
                    <td className="py-3.5 px-4">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-mono border ${getQualityBadge(item.quality)}`}>
                        {item.quality || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-300">
                      {item.sentiment || 'Neutral'}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-brand-amber font-medium">
                      ${item.cost_usd ? item.cost_usd.toFixed(4) : '0.0000'}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => onInspectCall(item.interaction_id)}
                        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-brand-cyan border border-cyan-500/30 text-xs font-medium transition-all"
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
        <div className="p-4 border-t border-slate-800/80 bg-slate-950/40 flex items-center justify-between text-xs text-slate-400">
          <div>
            Showing page <span className="font-mono text-slate-200">{page}</span> of <span className="font-mono text-slate-200">{pages}</span> ({total} total calls)
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(pages, p + 1))}
              disabled={page >= pages}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

