import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import AudioPlayer from '../components/AudioPlayer';
import TimelineTurnCard from '../components/TimelineTurnCard';
import EvaluationCard from '../components/EvaluationCard';
import ReviewModal from '../components/ReviewModal';
import {
  Phone,
  Clock,
  Activity,
  Layers,
  Sparkles,
  ShieldCheck,
  UserCheck,
  RefreshCw,
  Search,
  Filter,
  DollarSign,
  AlertCircle
} from 'lucide-react';

export default function DrillDownView({ initialCallId, onSelectCallId }) {
  const [callList, setCallList] = useState([]);
  const [selectedCallId, setSelectedCallId] = useState(initialCallId || '');
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState(null);

  // Call Data
  const [timeline, setTimeline] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [currentTime, setCurrentTime] = useState(0);
  const [seekTarget, setSeekTarget] = useState(null);

  // Filters for timeline
  const [speakerFilter, setSpeakerFilter] = useState('all');
  const [turnSearch, setTurnSearch] = useState('');

  // Review Modal State
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [targetEvaluation, setTargetEvaluation] = useState(null);

  // 1. Load call list on mount
  useEffect(() => {
    async function fetchCalls() {
      try {
        const calls = await api.getInteractionsList();
        setCallList(calls || []);
        if (!selectedCallId && calls && calls.length > 0) {
          const first = calls[0].interaction_id || calls[0].id || calls[0];
          setSelectedCallId(first);
          if (onSelectCallId) onSelectCallId(first);
        }
      } catch (err) {
        console.error('Failed to load call list:', err);
      }
    }
    fetchCalls();
  }, []);

  // Update if initialCallId changed from outside (e.g. clicking Inspect in table)
  useEffect(() => {
    if (initialCallId && initialCallId !== selectedCallId) {
      setSelectedCallId(initialCallId);
    }
  }, [initialCallId]);

  // 2. Load call details when selectedCallId changes
  useEffect(() => {
    if (!selectedCallId) return;
    loadCallData(selectedCallId);
  }, [selectedCallId]);

  async function loadCallData(id) {
    setLoading(true);
    setError(null);
    setCurrentTime(0);
    setSeekTarget(null);
    try {
      const [tlData, evalsData, revsData] = await Promise.all([
        api.getTimeline(id).catch((e) => {
          console.warn('Timeline error:', e);
          return null;
        }),
        api.getEvaluations(id).catch((e) => {
          console.warn('Evaluations error:', e);
          return [];
        }),
        api.listReviews(id).catch((e) => {
          console.warn('Reviews error:', e);
          return [];
        }),
      ]);

      setTimeline(tlData);
      setEvaluations(evalsData || []);
      setReviews(revsData || []);
    } catch (err) {
      console.error('Error fetching interaction details:', err);
      setError(err.message || 'Failed to load interaction details');
    } finally {
      setLoading(false);
    }
  }

  const handleReevaluate = async () => {
    if (!selectedCallId) return;
    setEvaluating(true);
    try {
      const newEvals = await api.evaluate(selectedCallId);
      setEvaluations(newEvals || []);
      // Also refresh timeline
      const tl = await api.getTimeline(selectedCallId).catch(() => null);
      if (tl) setTimeline(tl);
    } catch (e) {
      console.error('Failed to evaluate interaction:', e);
      alert('Evaluation error: ' + (e.message || 'Unknown error'));
    } finally {
      setEvaluating(false);
    }
  };

  const handleOpenAdjudicate = (ev) => {
    setTargetEvaluation(ev);
    setReviewModalOpen(true);
  };

  // Filter events
  const events = (timeline?.events || []).filter((e) => {
    if (speakerFilter !== 'all' && e.speaker !== speakerFilter) return false;
    if (turnSearch && !e.text?.toLowerCase().includes(turnSearch.toLowerCase())) return false;
    return true;
  });

  const audioUrl = selectedCallId ? api.getAudioUrl(selectedCallId) : '';

  return (
    <div className="space-y-6">
      {/* Top Bar with Dynamic Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Phone className="w-5 h-5" />
          </div>
          <div>
            <label className="text-[11px] font-mono text-slate-400 uppercase tracking-wider block">
              Active Interaction ID
            </label>
            <div className="flex items-center gap-2 mt-0.5">
              <select
                value={selectedCallId}
                onChange={(e) => {
                  const id = e.target.value;
                  setSelectedCallId(id);
                  if (onSelectCallId) onSelectCallId(id);
                }}
                className="bg-slate-950 border border-slate-800 text-sm font-mono text-cyan-400 font-medium rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500 cursor-pointer"
              >
                {callList.map((c) => {
                  const val = typeof c === 'string' ? c : (c.interaction_id || c.id);
                  return (
                    <option key={val} value={val}>
                      {val}
                    </option>
                  );
                })}
              </select>
              <button
                onClick={() => loadCallData(selectedCallId)}
                className="p-2 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                title="Reload Interaction"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleReevaluate}
            disabled={evaluating || !selectedCallId}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium bg-gradient-to-r from-cyan-500/20 to-brand-500/20 border border-cyan-500/30 text-cyan-300 hover:border-cyan-500/60 transition-all disabled:opacity-50"
          >
            <Sparkles className={`w-4 h-4 text-cyan-400 ${evaluating ? 'animate-spin' : ''}`} />
            <span>{evaluating ? 'Evaluating...' : 'Run Evaluators'}</span>
          </button>

          <button
            onClick={() => handleOpenAdjudicate(evaluations[0] || null)}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors shadow-lg shadow-cyan-500/10"
          >
            <UserCheck className="w-4 h-4" /> Adjudicate Call
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <div>
            <p className="font-medium">Error loading interaction</p>
            <p className="text-xs text-rose-400 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Audio Player */}
      <AudioPlayer
        audioUrl={audioUrl}
        currentTime={currentTime}
        onTimeUpdate={(t) => setCurrentTime(t)}
        onSeekTo={seekTarget}
      />

      {/* Metrics Strip */}
      {timeline && (
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Duration</span>
            <span className="text-base font-bold text-slate-100 font-mono mt-0.5 block">
              {timeline.total_duration_s ? `${timeline.total_duration_s.toFixed(1)}s` : 'N/A'}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Agent Turns</span>
            <span className="text-base font-bold text-cyan-400 font-mono mt-0.5 block">
              {timeline.agent_turn_count ?? 0}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Customer Turns</span>
            <span className="text-base font-bold text-emerald-400 font-mono mt-0.5 block">
              {timeline.customer_turn_count ?? 0}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Overlaps</span>
            <span className={`text-base font-bold font-mono mt-0.5 block ${(timeline.overlap_count || 0) > 0 ? 'text-amber-400' : 'text-slate-100'}`}>
              {timeline.overlap_count ?? 0} ({timeline.total_overlap_s?.toFixed(1) || 0}s)
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Technical Failure</span>
            <span className={`text-xs font-mono font-semibold mt-1 block truncate ${timeline.first_technical_failure ? 'text-rose-400' : 'text-emerald-400'}`}>
              {timeline.first_technical_failure ? timeline.first_technical_failure.failure_type : 'None detected'}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40">
            <span className="text-[10px] font-mono uppercase text-slate-500 block">Conversational Failure</span>
            <span className={`text-xs font-mono font-semibold mt-1 block truncate ${timeline.first_conversational_failure ? 'text-rose-400' : 'text-emerald-400'}`}>
              {timeline.first_conversational_failure ? timeline.first_conversational_failure.failure_type : 'None detected'}
            </span>
          </div>
        </div>
      )}

      {/* Main Split-Screen Grid: Timeline on Left, Evaluations on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Synchronized Timeline Turns (7 cols) */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">Reconstructed Chronological Timeline</h3>
              <span className="text-xs font-mono text-slate-500">({events.length} turns)</span>
            </div>

            {/* Filter pills */}
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="text"
                  placeholder="Filter text..."
                  value={turnSearch}
                  onChange={(e) => setTurnSearch(e.target.value)}
                  className="pl-8 pr-2.5 py-1 text-xs rounded-md bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-cyan-500 w-32 sm:w-40 font-mono"
                />
              </div>

              <select
                value={speakerFilter}
                onChange={(e) => setSpeakerFilter(e.target.value)}
                className="text-xs rounded-md bg-slate-950 border border-slate-800 text-slate-300 px-2 py-1 focus:outline-none focus:border-cyan-500 font-mono"
              >
                <option value="all">All Speakers</option>
                <option value="agent">Agent only</option>
                <option value="customer">Customer only</option>
              </select>
            </div>
          </div>

          {events.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-slate-800/80 bg-slate-900/30 text-slate-500 text-xs">
              No timeline turns found matching criteria or timeline not yet reconstructed.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[650px] overflow-y-auto pr-1">
              {events.map((ev, idx) => {
                const isActive =
                  currentTime >= (ev.start_s ?? 0) && currentTime <= (ev.end_s ?? Infinity);
                return (
                  <TimelineTurnCard
                    key={ev.event_id || idx}
                    event={ev}
                    isActive={isActive}
                    onSeek={(s) => setSeekTarget(s)}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Multi-Dimensional Evaluations & Reviews (5 cols) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Evaluations Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-semibold text-white">Evaluations &amp; Quality Dimensions</h3>
                <span className="text-xs font-mono text-slate-500">({evaluations.length})</span>
              </div>
            </div>

            {evaluations.length === 0 ? (
              <div className="p-6 text-center rounded-xl border border-slate-800/80 bg-slate-900/30 text-slate-500 text-xs">
                No evaluations recorded for this interaction yet. Click &ldquo;Run Evaluators&rdquo; above to execute live evaluation suite.
              </div>
            ) : (
              <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                {evaluations.map((ev, i) => (
                  <EvaluationCard
                    key={ev.evaluator_id || i}
                    evaluation={ev}
                    onOpenReview={handleOpenAdjudicate}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Human Review Adjudications Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white">Adjudication Audit Trail</h3>
                <span className="text-xs font-mono text-slate-500">({reviews.length})</span>
              </div>
            </div>

            {reviews.length === 0 ? (
              <div className="p-4 rounded-xl border border-slate-800/60 bg-slate-900/20 text-slate-500 text-xs">
                No human adjudications logged yet. Adjudications will appear here as reviewers accept or override model verdicts.
              </div>
            ) : (
              <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                {reviews.map((r, i) => (
                  <div key={r.review_id || i} className="p-3 rounded-lg bg-slate-900/70 border border-slate-800 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-cyan-400 font-semibold">{r.evaluator_id}</span>
                      <span className={`px-2 py-0.5 rounded-full font-mono text-[10px] ${
                        r.review_decision === 'OVERRIDDEN'
                          ? 'bg-amber-950/70 text-amber-400 border border-amber-600/30'
                          : 'bg-emerald-950/70 text-emerald-400 border border-emerald-600/30'
                      }`}>
                        {r.review_decision}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400 text-[11px] mb-1">
                      <span>Label: <strong className="text-slate-200">{r.reviewed_label}</strong></span>
                      <span>&bull;</span>
                      <span>By: <span className="text-slate-300">{r.reviewer_name}</span></span>
                    </div>
                    {r.notes && <p className="text-slate-300 text-[11px] italic">&ldquo;{r.notes}&rdquo;</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Adjudication Modal */}
      <ReviewModal
        isOpen={reviewModalOpen}
        onClose={() => setReviewModalOpen(false)}
        callId={selectedCallId}
        evaluation={targetEvaluation}
        onSuccess={() => loadCallData(selectedCallId)}
      />
    </div>
  );
}

