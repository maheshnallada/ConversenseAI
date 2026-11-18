import React, { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  Server,
  Zap,
  RotateCw,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Play,
  ArrowRight,
  Search,
  Activity,
  Cpu,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  Check,
} from 'lucide-react';
import { api } from '../api/client';

export default function ScalingView({ onInspectCall }) {
  const [stats, setStats] = useState(null);
  const [dlqItems, setDlqItems] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [errorMessage, setErrorMessage] = useState(null);

  // Stage Inspector State
  const [inspectInteractionId, setInspectInteractionId] = useState('');
  const [stagesData, setStagesData] = useState(null);
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectError, setInspectError] = useState(null);

  // Replay State
  const [replayingIds, setReplayingIds] = useState(new Set());
  const [replayedSuccessIds, setReplayedSuccessIds] = useState(new Set());

  const fetchData = useCallback(async () => {
    try {
      setErrorMessage(null);
      const [queueStats, dlqList] = await Promise.all([
        api.getQueueStats(),
        api.getDLQ(50),
      ]);
      setStats(queueStats);
      setDlqItems(dlqList);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to fetch queue statistics');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Auto-refresh interval (every 3 seconds)
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchData();
    }, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchData]);

  const handleManualRefresh = () => {
    setIsRefreshing(true);
    fetchData();
  };

  const handleInspectStages = async (callId) => {
    const targetId = callId || inspectInteractionId.trim();
    if (!targetId) return;
    setInspectInteractionId(targetId);
    setIsInspecting(true);
    setInspectError(null);
    try {
      const data = await api.getInteractionStages(targetId);
      setStagesData(data);
    } catch (err) {
      setInspectError(err.message || 'Failed to load stage timeline');
      setStagesData(null);
    } finally {
      setIsInspecting(false);
    }
  };

  const handleReplayJob = async (interactionId, stage = 'general') => {
    setReplayingIds((prev) => new Set(prev).add(interactionId));
    try {
      await api.replayQueueJob(interactionId, stage);
      setReplayedSuccessIds((prev) => new Set(prev).add(interactionId));
      setTimeout(() => {
        setReplayedSuccessIds((prev) => {
          const next = new Set(prev);
          next.delete(interactionId);
          return next;
        });
      }, 3000);
      await fetchData();
    } catch (err) {
      alert(`Replay failed for ${interactionId}: ${err.message}`);
    } finally {
      setReplayingIds((prev) => {
        const next = new Set(prev);
        next.delete(interactionId);
        return next;
      });
    }
  };

  const queues = stats?.queues || {};
  const generalCount = queues['stream:general'] ?? 0;
  const evalCount = queues['stream:evaluation'] ?? 0;
  const analyticsCount = queues['stream:analytics'] ?? 0;
  const dlqCount = queues['stream:dlq'] ?? dlqItems.length;
  const brokerType = stats?.type === 'redis_streams' ? 'Redis 7 Streams' : 'In-Memory Broker';

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 p-5 rounded-2xl shadow-sm">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-500 dark:bg-cyan-400/10 dark:text-cyan-400">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
                Scaling & Queue Operations
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-400 border border-emerald-500/20">
                  Live
                </span>
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Decoupled worker streams, transactional outbox dispatch, and DLQ replay management
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Broker Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-xs font-medium text-slate-700 dark:text-slate-300">
            <Server className="w-3.5 h-3.5 text-cyan-500" />
            <span>{brokerType}</span>
          </div>

          {/* Auto Refresh Toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors border ${
              autoRefresh
                ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700'
            }`}
          >
            <Activity className={`w-3.5 h-3.5 ${autoRefresh ? 'animate-pulse text-emerald-500' : ''}`} />
            Auto-refresh: {autoRefresh ? '3s' : 'Off'}
          </button>

          {/* Manual Refresh Button */}
          <button
            onClick={handleManualRefresh}
            disabled={isRefreshing}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition"
            title="Refresh statistics"
          >
            <RotateCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/60 text-rose-700 dark:text-rose-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Stream KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* General Queue */}
        <div className="bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              General Stream
            </span>
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500 dark:bg-blue-400/10 dark:text-blue-400">
              <Zap className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {isLoading ? '...' : generalCount}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Reconstruction & Observability
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] text-blue-600 dark:text-blue-400 font-medium">
            <Clock className="w-3 h-3" />
            <span>Target: p95 &lt; 5s</span>
          </div>
        </div>

        {/* Evaluation Queue */}
        <div className="bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Evaluation Stream
            </span>
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-500 dark:bg-indigo-400/10 dark:text-indigo-400">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {isLoading ? '...' : evalCount}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Parallel LLM Batches 1, 2, 3
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] text-indigo-600 dark:text-indigo-400 font-medium">
            <ShieldCheck className="w-3 h-3" />
            <span>Concurrency Cap: 15 slots</span>
          </div>
        </div>

        {/* Analytics Queue */}
        <div className="bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 p-5 rounded-2xl shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Analytics Stream
            </span>
            <div className="p-2 rounded-lg bg-teal-500/10 text-teal-500 dark:bg-teal-400/10 dark:text-teal-400">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {isLoading ? '...' : analyticsCount}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Dashboard Read Models & Cache
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] text-teal-600 dark:text-teal-400 font-medium">
            <CheckCircle2 className="w-3 h-3" />
            <span>Asynchronous Fan-out</span>
          </div>
        </div>

        {/* Dead Letter Queue */}
        <div className={`p-5 rounded-2xl shadow-sm border transition relative overflow-hidden ${
          dlqCount > 0
            ? 'bg-amber-50/50 dark:bg-amber-950/20 border-amber-300 dark:border-amber-800/60'
            : 'bg-white dark:bg-[#0c1322] border-slate-200 dark:border-slate-800'
        }`}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Dead Letter Queue
            </span>
            <div className={`p-2 rounded-lg ${
              dlqCount > 0
                ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
            }`}>
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className={`text-2xl font-bold ${dlqCount > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-900 dark:text-slate-100'}`}>
            {isLoading ? '...' : dlqCount}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Persistent Failures (Max Retries)
          </p>
          <div className="mt-3 flex items-center gap-1.5 text-[11px] text-amber-600 dark:text-amber-400 font-medium">
            <RotateCw className="w-3 h-3" />
            <span>{dlqCount > 0 ? 'Replay available' : 'Queue clean'}</span>
          </div>
        </div>
      </div>

      {/* Dead Letter Queue Management Table */}
      <div className="bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <span>Dead-Letter Queue (DLQ) &amp; Error Triage</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                {dlqItems.length} jobs
              </span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Interactions that exhausted retries or encountered unrecoverable exceptions. Click Replay to re-enqueue.
            </p>
          </div>
        </div>

        {dlqItems.length === 0 ? (
          <div className="py-12 text-center text-slate-500 dark:text-slate-400">
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500 mb-2 opacity-80" />
            <p className="text-sm font-medium">No dead-lettered jobs</p>
            <p className="text-xs text-slate-400 mt-1">All worker pipelines are processing normally without unhandled failures.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="py-3 px-4 font-semibold">Interaction ID</th>
                  <th className="py-3 px-4 font-semibold">Failed Stage</th>
                  <th className="py-3 px-4 font-semibold">Retries</th>
                  <th className="py-3 px-4 font-semibold">Diagnostic Error</th>
                  <th className="py-3 px-4 font-semibold">Failed At</th>
                  <th className="py-3 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 font-mono">
                {dlqItems.map((item) => {
                  const isReplaying = replayingIds.has(item.interaction_id);
                  const isSuccess = replayedSuccessIds.has(item.interaction_id);

                  return (
                    <tr key={item.interaction_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition">
                      <td className="py-3 px-4 font-medium text-slate-900 dark:text-slate-100">
                        <button
                          onClick={() => handleInspectStages(item.interaction_id)}
                          className="hover:text-cyan-500 underline decoration-slate-300 dark:decoration-slate-700 underline-offset-2 transition"
                        >
                          {item.interaction_id}
                        </button>
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded-full text-[11px] font-sans font-medium bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">
                          {item.stage_name}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-600 dark:text-slate-400 font-sans">
                        {item.retry_count}
                      </td>
                      <td className="py-3 px-4 text-rose-600 dark:text-rose-400 max-w-xs truncate font-sans" title={item.last_error}>
                        {item.last_error || 'Unknown error'}
                      </td>
                      <td className="py-3 px-4 text-slate-500 dark:text-slate-400 font-sans whitespace-nowrap">
                        {item.failed_at ? new Date(item.failed_at).toLocaleTimeString() : '—'}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-2 font-sans">
                          <button
                            onClick={() => handleInspectStages(item.interaction_id)}
                            className="px-2.5 py-1 text-xs rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition"
                          >
                            Inspect
                          </button>
                          <button
                            onClick={() => handleReplayJob(item.interaction_id, item.stage_name)}
                            disabled={isReplaying || isSuccess}
                            className={`flex items-center gap-1.5 px-3 py-1 text-xs rounded-lg font-medium transition ${
                              isSuccess
                                ? 'bg-emerald-600 text-white'
                                : 'bg-cyan-600 hover:bg-cyan-700 text-white disabled:opacity-50'
                            }`}
                          >
                            {isReplaying ? (
                              <RotateCw className="w-3.5 h-3.5 animate-spin" />
                            ) : isSuccess ? (
                              <>
                                <Check className="w-3.5 h-3.5" />
                                <span>Replayed</span>
                              </>
                            ) : (
                              <>
                                <Play className="w-3 h-3 fill-current" />
                                <span>Replay</span>
                              </>
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Interactive Stage Timeline Inspector */}
      <div className="bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <Layers className="w-5 h-5 text-cyan-500" />
              <span>Pipeline Stage Inspector</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Inspect granular execution latencies, retry state, and outcomes across pipeline stages
            </p>
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <div className="relative flex-1 sm:w-72">
              <input
                type="text"
                placeholder="Enter interaction ID..."
                value={inspectInteractionId}
                onChange={(e) => setInspectInteractionId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleInspectStages()}
                className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-cyan-500/40"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            </div>
            <button
              onClick={() => handleInspectStages()}
              disabled={isInspecting || !inspectInteractionId.trim()}
              className="px-3.5 py-1.5 text-xs font-semibold rounded-xl bg-cyan-600 hover:bg-cyan-700 text-white disabled:opacity-50 transition"
            >
              {isInspecting ? 'Loading...' : 'Inspect'}
            </button>
          </div>
        </div>

        {inspectError && (
          <div className="mt-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs">
            {inspectError}
          </div>
        )}

        {stagesData ? (
          <div className="mt-5 space-y-4">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-500 dark:text-slate-400">Interaction ID:</span>
                <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">
                  {stagesData.interaction_id}
                </span>
              </div>
              {onInspectCall && (
                <button
                  onClick={() => onInspectCall(stagesData.interaction_id)}
                  className="flex items-center gap-1 text-cyan-600 dark:text-cyan-400 hover:underline font-medium"
                >
                  <span>Open in Call Drill-Down</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Stages Stepper Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {['general', 'evaluation', 'analytics'].map((stageKey) => {
                const stage = (stagesData.stages || []).find((s) => s.stage_name === stageKey);
                const status = stage?.status || 'pending';

                const statusStyles = {
                  completed: 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-400 border-emerald-500/30',
                  running: 'bg-blue-500/10 text-blue-600 dark:bg-blue-400/10 dark:text-blue-400 border-blue-500/30 animate-pulse',
                  failed: 'bg-rose-500/10 text-rose-600 dark:bg-rose-400/10 dark:text-rose-400 border-rose-500/30',
                  dead_letter: 'bg-amber-500/10 text-amber-600 dark:bg-amber-400/10 dark:text-amber-400 border-amber-500/30',
                  pending: 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 border-slate-200 dark:border-slate-700',
                };

                return (
                  <div
                    key={stageKey}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/40 relative"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">
                        {stageKey === 'general' ? '1. Reconstruction' : stageKey === 'evaluation' ? '2. LLM Evaluation' : '3. Analytics'}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${statusStyles[status]}`}>
                        {status}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs text-slate-600 dark:text-slate-400 mt-3">
                      <div className="flex items-center justify-between">
                        <span>Duration:</span>
                        <span className="font-mono font-medium text-slate-900 dark:text-slate-100">
                          {stage?.duration_ms ? `${stage.duration_ms.toFixed(1)} ms` : '—'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span>Retries:</span>
                        <span className="font-mono">{stage?.retry_count ?? 0} / {stage?.max_retries ?? 3}</span>
                      </div>
                      {stage?.last_error && (
                        <div className="mt-2 p-2 rounded bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/60 text-[11px] text-rose-600 dark:text-rose-400 truncate">
                          {stage.last_error}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-slate-400">
            Enter an Interaction ID above or click any interaction from the Dead-Letter Queue to inspect its stage breakdown.
          </div>
        )}
      </div>
    </div>
  );
}
