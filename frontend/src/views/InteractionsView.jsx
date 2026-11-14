import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { Search, ChevronLeft, ChevronRight, Eye } from 'lucide-react';

export default function InteractionsView({ onInspectCall }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const requestId = useRef(0);

  const [search, setSearch] = useState('');
  const [outcome, setOutcome] = useState('');
  const [status, setStatus] = useState('');
  const [useCase, setUseCase] = useState('');
  const [startedAfter, setStartedAfter] = useState('');
  const [startedBefore, setStartedBefore] = useState('');
  const [errorState, setErrorState] = useState('');

  useEffect(() => {
    loadInteractions(page);
  }, [page, outcome, status, useCase, startedAfter, startedBefore, errorState]);

  async function loadInteractions(p = 1) {
    const currentRequestId = ++requestId.current;
    setLoading(true);
    setError(null);
    setItems([]);
    setTotal(0);
    setPages(1);
    try {
      const params = { page: p, page_size: 10 };
      if (search) params.search = search;
      if (outcome) params.outcome = outcome;
      if (status) params.status = status;
      if (useCase) params.use_case = useCase;
      if (startedAfter) params.started_after = `${startedAfter}T00:00:00Z`;
      if (startedBefore) params.started_before = `${startedBefore}T23:59:59.999999Z`;
      if (errorState) params.error_state = errorState;

      const data = await api.getInteractionsPage(params);
      if (currentRequestId !== requestId.current) return;
      setItems(data.items || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
      setPage(data.page || 1);
    } catch (e) {
      if (currentRequestId !== requestId.current) return;
      console.error('Failed to load interactions:', e);
      setError(e.message || 'Failed to load interactions.');
    } finally {
      if (currentRequestId === requestId.current) setLoading(false);
    }
  }

  function updateFilter(setter) {
    return (event) => {
      setter(event.target.value);
      setPage(1);
    };
  }

  function handleSearchSubmit(e) {
    e.preventDefault();
    if (page !== 1) setPage(1);
    else loadInteractions(1);
  }

  return (
    <div className="space-y-4">
      <div className="p-4 rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none space-y-3">
        <form onSubmit={handleSearchSubmit} className="relative min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search interaction ID or call alias..."
            className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-900 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:border-cyan-500 font-mono"
          />
        </form>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <label className="text-[11px] text-slate-500">
            From
            <input type="date" value={startedAfter} onChange={updateFilter(setStartedAfter)} className="ml-1 px-2 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300" />
          </label>
          <label className="text-[11px] text-slate-500">
            To
            <input type="date" value={startedBefore} onChange={updateFilter(setStartedBefore)} className="ml-1 px-2 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300" />
          </label>
          <input
            type="text"
            value={useCase}
            onChange={updateFilter(setUseCase)}
            placeholder="Use case"
            aria-label="Filter by use case"
            className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300"
          />
          <select value={status} onChange={updateFilter(setStatus)} aria-label="Filter by processing status" className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300">
            <option value="">All processing statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="abandoned">Abandoned</option>
            <option value="pending">Pending</option>
            <option value="unknown">Unknown</option>
          </select>
          <select value={outcome} onChange={updateFilter(setOutcome)} aria-label="Filter by evaluation outcome" className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300">
            <option value="">All outcomes</option>
            <option value="Not interested">Not interested</option>
            <option value="Callback Requested">Callback Requested</option>
            <option value="Expert Call Booked">Expert Call Booked</option>
            <option value="Call later">Call later</option>
            <option value="Do not call">Do not call</option>
            <option value="Voicemail">Voicemail</option>
          </select>
          <select value={errorState} onChange={updateFilter(setErrorState)} aria-label="Filter by error state" className="px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300">
            <option value="">All error states</option>
            <option value="has_errors">Has errors</option>
            <option value="no_errors">No errors</option>
          </select>
        </div>
      </div>

      <div className="rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-none overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs min-w-[760px]">
            <thead className="bg-slate-50 dark:bg-slate-950/60 border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 font-mono uppercase tracking-wider text-[10px]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">Interaction</th>
                <th className="py-3.5 px-4 font-semibold">Start time</th>
                <th className="py-3.5 px-4 font-semibold">Use case</th>
                <th className="py-3.5 px-4 font-semibold">Processing status</th>
                <th className="py-3.5 px-4 font-semibold">Evaluation outcome</th>
                <th className="py-3.5 px-4 font-semibold">Errors</th>
                <th className="py-3.5 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 font-sans">
              {loading ? (
                <tr><td colSpan="7" className="py-12 text-center text-slate-500">Loading interactions...</td></tr>
              ) : error ? (
                <tr>
                  <td colSpan="7" className="py-12 text-center text-rose-600 dark:text-rose-400">
                    <p>{error}</p>
                    <button onClick={() => loadInteractions(page)} className="mt-2 px-3 py-1 rounded-lg bg-rose-100 dark:bg-rose-950/60 font-semibold">Retry</button>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr><td colSpan="7" className="py-12 text-center text-slate-400">No interactions match the selected filters.</td></tr>
              ) : (
                items.map((item) => (
                  <tr key={item.interaction_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30">
                    <td className="py-3.5 px-4">
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{item.folder_name || 'Interaction'}</div>
                      <div className="font-mono text-[11px] text-slate-500 truncate max-w-[180px]" title={item.interaction_id}>{item.interaction_id}</div>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-600 dark:text-slate-300">
                      {item.started_at ? new Date(item.started_at).toLocaleString() : 'Unavailable'}
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300">{item.use_case || 'Unavailable'}</td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300">{item.status || 'Unknown'}</td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300">{item.outcome || 'Unavailable'}</td>
                    <td className="py-3.5 px-4 text-slate-600 dark:text-slate-300">{item.has_errors == null ? 'Unknown' : item.has_errors ? 'Yes' : 'No'}</td>
                    <td className="py-3.5 px-4 text-right">
                      <button onClick={() => onInspectCall(item.interaction_id)} className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cyan-50 hover:bg-cyan-100 text-cyan-700 border border-cyan-200 dark:bg-cyan-500/10 dark:hover:bg-cyan-500/20 dark:text-cyan-400 dark:border-cyan-500/30 text-xs font-semibold">
                        <Eye className="w-3.5 h-3.5" /> Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
          <div className="text-slate-500">Showing <strong className="text-slate-800 dark:text-slate-200">{items.length}</strong> of <strong className="text-slate-800 dark:text-slate-200">{total}</strong> interactions</div>
          <div className="flex items-center gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 disabled:opacity-40"><ChevronLeft className="w-4 h-4" /></button>
            <span className="text-slate-700 dark:text-slate-300 px-2">Page {page} of {pages}</span>
            <button onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page >= pages} className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 disabled:opacity-40"><ChevronRight className="w-4 h-4" /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
