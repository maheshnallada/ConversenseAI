import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import AudioPlayer from '../components/AudioPlayer';
import TimelineTurnCard from '../components/TimelineTurnCard';
import TimelineMarker from '../components/TimelineMarker';
import EvaluationCard from '../components/EvaluationCard';
import ReviewModal from '../components/ReviewModal';
import {
  Phone,
  Layers,
  Sparkles,
  ShieldCheck,
  UserCheck,
  RefreshCw,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  FolderOpen
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

  // Timeline UI filters & controls
  const [speakerFilter, setSpeakerFilter] = useState('all'); // 'all', 'agent', 'customer'
  const [deliveryFilter, setDeliveryFilter] = useState('all'); // 'all', 'heard', 'cut', 'not_played'
  const [turnSearch, setTurnSearch] = useState('');
  const [expandAllDetails, setExpandAllDetails] = useState(null); // null, true, false

  // Review Modal State
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [targetEvaluation, setTargetEvaluation] = useState(null);

  // 1. Fetch available calls on mount
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

  // Update when initialCallId changes from explorer/ingest
  useEffect(() => {
    if (initialCallId && initialCallId !== selectedCallId) {
      setSelectedCallId(initialCallId);
    }
  }, [initialCallId]);

  // 2. Load call data on selectedCallId change
  useEffect(() => {
    if (!selectedCallId) return;
    loadCallData(selectedCallId);
  }, [selectedCallId]);

  async function loadCallData(id) {
    setLoading(true);
    setError(null);
    setCurrentTime(0);
    setSeekTarget(null);
    setExpandAllDetails(null);
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

  // Next / Previous navigation
  const currentIndex = callList.findIndex((c) => {
    const val = typeof c === 'string' ? c : (c.interaction_id || c.id);
    return val === selectedCallId;
  });

  const handlePrevCall = () => {
    if (currentIndex > 0) {
      const prev = callList[currentIndex - 1];
      const val = typeof prev === 'string' ? prev : (prev.interaction_id || prev.id);
      setSelectedCallId(val);
      if (onSelectCallId) onSelectCallId(val);
    }
  };

  const handleNextCall = () => {
    if (currentIndex < callList.length - 1) {
      const next = callList[currentIndex + 1];
      const val = typeof next === 'string' ? next : (next.interaction_id || next.id);
      setSelectedCallId(val);
      if (onSelectCallId) onSelectCallId(val);
    }
  };

  const handleReevaluate = async () => {
    if (!selectedCallId) return;
    setEvaluating(true);
    try {
      const newEvals = await api.evaluate(selectedCallId);
      setEvaluations(newEvals || []);
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

  const formatFailureLabel = (str) => {
    if (!str || str.toLowerCase() === 'none') return 'None';
    return str
      .toLowerCase()
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  // Filter events
  const rawEvents = timeline?.events || [];
  const filteredEvents = rawEvents.filter((e) => {
    if (e.event_type === 'interruption' || e.event_type === 'silence') {
      return true;
    }
    if (speakerFilter !== 'all' && e.speaker !== speakerFilter) return false;

    if (deliveryFilter !== 'all') {
      const st = (e.delivery_status || e.metadata?.playback_spoken || '').toLowerCase();
      if (deliveryFilter === 'cut' && !st.includes('cut')) return false;
      if (deliveryFilter === 'heard' && st !== 'heard') return false;
      if (deliveryFilter === 'not_played' && st !== 'not_played') return false;
    }

    if (turnSearch) {
      const q = turnSearch.toLowerCase();
      const txt = (e.text || '').toLowerCase();
      const norm = (e.metadata?.normalized_text || '').toLowerCase();
      if (!txt.includes(q) && !norm.includes(q)) return false;
    }
    return true;
  });

  const audioUrl = selectedCallId ? api.getAudioUrl(selectedCallId) : '';

  // Extract primary outcome and quality summary from evaluations
  const outcomeEval = evaluations.find((ev) => ev.evaluator_id === 'outcome.intent' || ev.family === 'outcome');
  const qualityEval = evaluations.find((ev) => ev.evaluator_id === 'quality.scorecard' || ev.family === 'quality');
  const experienceEval = evaluations.find((ev) => ev.evaluator_id === 'experience.sentiment_emotion' || ev.family === 'experience');
  const complianceEval = evaluations.find((ev) => ev.evaluator_id === 'compliance.never_rules' || ev.family === 'compliance');

  return (
    <div className="space-y-4">
      {/* 1. Top Hero Command Bar */}
      <div className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 shadow-sm dark:shadow-none transition-colors space-y-3.5">
        {/* Top Controls Row: Selector on Left, Actions on Right */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-slate-800/80">
          {/* Interaction Dropdown & Steppers */}
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <FolderOpen className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              <span className="hidden sm:inline">Call</span>
              <span>{currentIndex + 1} of {callList.length || 0}:</span>
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={handlePrevCall}
                disabled={currentIndex <= 0}
                className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 disabled:opacity-40 transition-colors border border-slate-200 dark:border-slate-700/60 shadow-sm"
                title="Previous interaction"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <select
                value={selectedCallId}
                onChange={(e) => {
                  const id = e.target.value;
                  setSelectedCallId(id);
                  if (onSelectCallId) onSelectCallId(id);
                }}
                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 text-xs sm:text-sm font-sans text-cyan-800 dark:text-cyan-400 font-bold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500 cursor-pointer max-w-[220px] sm:max-w-xs truncate"
              >
                {callList.map((c) => {
                  const val = typeof c === 'string' ? c : (c.interaction_id || c.id);
                  const label = typeof c === 'object' && (c.display_name || c.folder_name)
                    ? (c.display_name || c.folder_name)
                    : val;
                  return (
                    <option key={val} value={val}>
                      {label}
                    </option>
                  );
                })}
              </select>

              <button
                onClick={handleNextCall}
                disabled={currentIndex >= callList.length - 1}
                className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 disabled:opacity-40 transition-colors border border-slate-200 dark:border-slate-700/60 shadow-sm"
                title="Next interaction"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={() => loadCallData(selectedCallId)}
                className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors border border-slate-200 dark:border-slate-700/60 shadow-sm"
                title="Reload interaction"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleReevaluate}
              disabled={evaluating || !selectedCallId}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border border-cyan-200 dark:bg-cyan-500/10 dark:hover:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 transition-all disabled:opacity-50 shadow-sm"
            >
              <Sparkles className={`w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400 ${evaluating ? 'animate-spin' : ''}`} />
              <span>{evaluating ? 'Evaluating...' : 'Run Evaluators'}</span>
            </button>

            <button
              onClick={() => handleOpenAdjudicate(evaluations[0] || null)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors shadow-md shadow-cyan-500/20"
            >
              <UserCheck className="w-3.5 h-3.5" /> Adjudicate
            </button>
          </div>
        </div>

        {/* Bottom Executive Status Strip */}
        <div className="flex flex-wrap items-center gap-2">
          {outcomeEval && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Outcome:</span>
              <span className="text-slate-900 dark:text-white font-bold">{outcomeEval.label || 'Unknown'}</span>
            </div>
          )}

          {qualityEval && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Quality:</span>
              <span className={`font-bold ${
                qualityEval.label === 'Good' ? 'text-emerald-600 dark:text-emerald-400' : qualityEval.label === 'OK' ? 'text-amber-600 dark:text-amber-400' : 'text-rose-600 dark:text-rose-400'
              }`}>
                {qualityEval.label || qualityEval.review_status}
              </span>
            </div>
          )}

          {experienceEval && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Emotion:</span>
              <span className="text-cyan-700 dark:text-cyan-300 font-bold capitalize">{experienceEval.label || 'Neutral'}</span>
            </div>
          )}

          {complianceEval && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans flex items-center gap-1.5 whitespace-nowrap shadow-sm">
              <span className="text-slate-500">Never-Rules:</span>
              <span className={`font-bold ${complianceEval.review_status === 'PASSED' ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                {complianceEval.review_status}
              </span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Audio Player */}
      <AudioPlayer
        audioUrl={audioUrl}
        currentTime={currentTime}
        onTimeUpdate={(t) => setCurrentTime(t)}
        onSeekTo={seekTarget}
      />

      {/* 3. Telemetry Diagnostic Strip */}
      {timeline && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Duration</span>
            <span className="text-sm font-bold font-sans text-slate-900 dark:text-slate-100 mt-0.5 block">
              {timeline.total_duration_s ? `${timeline.total_duration_s.toFixed(1)}s` : 'N/A'}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Agent Turns</span>
            <span className="text-sm font-bold font-sans text-cyan-600 dark:text-cyan-400 mt-0.5 block">
              {timeline.agent_turn_count ?? 0}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Customer Turns</span>
            <span className="text-sm font-bold font-sans text-emerald-600 dark:text-emerald-400 mt-0.5 block">
              {timeline.customer_turn_count ?? 0}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Speech Overlaps</span>
            <span className={`text-sm font-bold font-sans mt-0.5 block ${(timeline.overlap_count || 0) > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-800 dark:text-slate-200'}`}>
              {timeline.overlap_count ?? 0} ({timeline.total_overlap_s?.toFixed(1) || 0}s)
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Tech Failure</span>
            <span
              className={`text-xs font-sans font-bold mt-1 block truncate ${
                timeline.first_technical_failure ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
              }`}
              title={timeline.first_technical_failure?.failure_type}
            >
              {formatFailureLabel(timeline.first_technical_failure?.failure_type)}
            </span>
          </div>

          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none">
            <span className="text-[10px] font-sans text-slate-500 uppercase block font-semibold">Conversational Issue</span>
            <span
              className={`text-xs font-sans font-bold mt-1 block truncate ${
                timeline.first_conversational_failure ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
              }`}
              title={timeline.first_conversational_failure?.failure_type}
            >
              {formatFailureLabel(timeline.first_conversational_failure?.failure_type)}
            </span>
          </div>
        </div>
      )}

      {/* 4. Main Two-Column Master View: Reconstructed Timeline on Left (7 cols), Observability Deck on Right (5 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Reconstructed Chronological Conversation Timeline */}
        <div className="lg:col-span-7 space-y-3">
          {/* Timeline Toolbar */}
          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 backdrop-blur-md shadow-sm dark:shadow-none flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                Conversation Stream
              </h3>
              <span className="text-xs text-slate-400 dark:text-slate-500">
                ({filteredEvents.length} items)
              </span>
            </div>

            {/* Quick Toggle All Details */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setExpandAllDetails(expandAllDetails === true ? false : true)}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-xs font-sans text-cyan-700 dark:text-cyan-400 border border-slate-200 dark:border-slate-700 transition-colors font-semibold shadow-sm"
                title="Toggle all turn inspector drawers"
              >
                {expandAllDetails === true ? (
                  <>
                    <ChevronUp className="w-3.5 h-3.5" /> Collapse All Details
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3.5 h-3.5" /> Expand All Details
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Filter Pills & Search */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 text-xs">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-slate-500 mr-1 font-semibold">Speaker:</span>
              {['all', 'agent', 'customer'].map((spk) => (
                <button
                  key={spk}
                  onClick={() => setSpeakerFilter(spk)}
                  className={`px-2.5 py-1 rounded-lg font-sans text-xs transition-all capitalize ${
                    speakerFilter === spk
                      ? 'bg-cyan-50 text-cyan-800 border border-cyan-300 dark:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 font-bold'
                      : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-white shadow-sm'
                  }`}
                >
                  {spk}
                </button>
              ))}

              <span className="text-xs text-slate-500 ml-2 mr-1 font-semibold">Status:</span>
              {['all', 'heard', 'cut', 'not_played'].map((st) => (
                <button
                  key={st}
                  onClick={() => setDeliveryFilter(st)}
                  className={`px-2.5 py-1 rounded-lg font-sans text-xs transition-all capitalize ${
                    deliveryFilter === st
                      ? 'bg-cyan-50 text-cyan-800 border border-cyan-300 dark:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 font-bold'
                      : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-white shadow-sm'
                  }`}
                >
                  {st.replace('_', ' ')}
                </button>
              ))}
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search turns / words..."
                value={turnSearch}
                onChange={(e) => setTurnSearch(e.target.value)}
                className="pl-8 pr-2.5 py-1 text-xs rounded-lg bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 w-44 font-sans shadow-sm"
              />
            </div>
          </div>

          {/* Conversation Stream */}
          {filteredEvents.length === 0 ? (
            <div className="p-8 text-center rounded-2xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/30 text-slate-500 text-xs shadow-sm">
              No matching conversation turns found for current filters.
            </div>
          ) : (
            <div className="space-y-3 max-h-[720px] overflow-y-auto pr-1">
              {filteredEvents.map((ev, idx) => {
                if (ev.event_type === 'interruption' || ev.event_type === 'silence') {
                  return (
                    <TimelineMarker
                      key={ev.event_id || `marker_${idx}`}
                      event={ev}
                      onSeek={(s) => setSeekTarget(s)}
                    />
                  );
                }

                const isActive =
                  currentTime >= (ev.start_s ?? 0) && currentTime <= (ev.end_s ?? Infinity);

                return (
                  <TimelineTurnCard
                    key={ev.event_id || `turn_${idx}`}
                    event={ev}
                    isActive={isActive}
                    onSeek={(s) => setSeekTarget(s)}
                    forceExpand={expandAllDetails}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Multi-Dimensional Observability Deck (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          {/* Evaluations Section */}
          <div className="space-y-3">
            <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 backdrop-blur-md shadow-sm dark:shadow-none flex items-center justify-between transition-colors">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                  Evaluations &amp; Quality Rubrics
                </h3>
              </div>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-semibold font-sans">
                {evaluations.length} Active
              </span>
            </div>

            {evaluations.length === 0 ? (
              <div className="p-6 text-center rounded-2xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/30 text-slate-500 text-xs shadow-sm">
                No evaluations recorded for this interaction yet. Click &ldquo;Run Evaluators&rdquo; above to run the 5-dimension suite.
              </div>
            ) : (
              <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
                {evaluations.map((ev, i) => (
                  <EvaluationCard
                    key={ev.evaluator_id || i}
                    evaluation={ev}
                    onOpenReview={handleOpenAdjudicate}
                    onSeek={(s) => setSeekTarget(s)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Adjudication Audit Trail Section */}
          <div className="space-y-3">
            <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 backdrop-blur-md shadow-sm dark:shadow-none flex items-center justify-between transition-colors">
              <div className="flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                  Human Adjudication Audit Trail
                </h3>
              </div>
              <button
                onClick={() => handleOpenAdjudicate(evaluations[0] || null)}
                className="text-xs font-sans text-cyan-600 hover:text-cyan-700 dark:text-cyan-400 dark:hover:text-cyan-300 font-semibold transition-colors"
              >
                + Add Review
              </button>
            </div>

            {reviews.length === 0 ? (
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800/60 bg-white dark:bg-slate-900/20 text-slate-500 text-xs shadow-sm font-sans">
                No human adjudications logged yet. Adjudications will appear here as reviewers accept or override model verdicts.
              </div>
            ) : (
              <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                {reviews.map((r, i) => (
                  <div key={r.review_id || i} className="p-3 rounded-xl bg-white dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800 text-xs shadow-sm dark:shadow-none font-sans">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-cyan-700 dark:text-cyan-400 font-bold">{r.evaluator_id}</span>
                      <span className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                        r.review_decision === 'OVERRIDDEN'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/70 dark:text-amber-400 dark:border-amber-600/30'
                          : 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/70 dark:text-emerald-400 dark:border-emerald-600/30'
                      }`}>
                        {r.review_decision}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-[11px] mb-1">
                      <span>Label: <strong className="text-slate-800 dark:text-slate-200">{r.reviewed_label}</strong></span>
                      <span>&bull;</span>
                      <span>By: <span className="text-slate-700 dark:text-slate-300">{r.reviewer_name}</span></span>
                    </div>
                    {r.notes && <p className="text-slate-600 dark:text-slate-300 text-[11px] italic">&ldquo;{r.notes}&rdquo;</p>}
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
