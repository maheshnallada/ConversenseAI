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
  FolderOpen,
  FileText,
  Activity,
  Clock,
  Award,
  CheckCircle2,
  XCircle,
  Calendar,
  DollarSign,
  Zap,
  Info,
  Check,
  Play
} from 'lucide-react';

function getDeliveryState(event) {
  const declaredStatus =
    typeof event.delivery_status === 'string' ? event.delivery_status : '';
  const playbackStatus =
    typeof event.metadata?.playback_spoken === 'string'
      ? event.metadata.playback_spoken
      : '';
  if (
    declaredStatus &&
    playbackStatus &&
    declaredStatus.toLowerCase() !== playbackStatus.toLowerCase()
  ) {
    return 'mismatch';
  }
  return declaredStatus || playbackStatus || 'unknown';
}

export default function DrillDownView({ initialCallId, onSelectCallId }) {
  const [callList, setCallList] = useState([]);
  const [selectedCallId, setSelectedCallId] = useState(initialCallId || '');
  const [loading, setLoading] = useState(false);
  const loadRequestId = useRef(0);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState(null);

  // Active Tab: 'details', 'observability', 'timeline', 'evaluation', 'semantic_evaluation'
  const [activeTab, setActiveTab] = useState('details');

  // Call Data
  const [interaction, setInteraction] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [observabilityData, setObservabilityData] = useState(null);
  const [evaluationRun, setEvaluationRun] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [audioUrl, setAudioUrl] = useState('');
  const [currentTime, setCurrentTime] = useState(0);
  const [seekTarget, setSeekTarget] = useState(null);

  // Timeline UI filters & controls
  const [speakerFilter, setSpeakerFilter] = useState('all'); // 'all', 'agent', 'customer'
  const [deliveryFilter, setDeliveryFilter] = useState('all');
  const [turnSearch, setTurnSearch] = useState('');
  const [expandAllDetails, setExpandAllDetails] = useState(null); // null, true, false

  // Review Modal State
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [targetEvaluation, setTargetEvaluation] = useState(null);

  function selectCallId(id) {
    loadRequestId.current += 1;
    setSelectedCallId(id);
    if (onSelectCallId) onSelectCallId(id);
  }

  // 1. Fetch available calls on mount
  useEffect(() => {
    async function fetchCalls() {
      try {
        const firstPage = await api.getInteractionsPage({
          page: 1,
          page_size: 100,
        });
        const pages = Array.from(
          { length: Math.max(0, (firstPage.pages || 1) - 1) },
          (_, index) => index + 2
        );
        const remainingPages = await Promise.all(
          pages.map((page) => api.getInteractionsPage({ page, page_size: 100 }))
        );
        const calls = [firstPage, ...remainingPages].flatMap(
          (page) => page.items || []
        );
        setCallList(calls);
        if (!selectedCallId && calls.length > 0) {
          const first = calls[0].interaction_id || calls[0].id || calls[0];
          selectCallId(first);
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
      selectCallId(initialCallId);
    }
  }, [initialCallId]);

  // 2. Load call data on selectedCallId change
  useEffect(() => {
    if (!selectedCallId) return;
    loadCallData(selectedCallId);
    return () => {
      loadRequestId.current += 1;
    };
  }, [selectedCallId]);

  useEffect(() => {
    let objectUrl;
    let cancelled = false;
    setAudioUrl('');
    if (!selectedCallId) return undefined;

    api
      .getAudioUrl(selectedCallId)
      .then((url) => {
        objectUrl = url;
        if (cancelled) {
          URL.revokeObjectURL(url);
        } else {
          setAudioUrl(url);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error('Failed to load call audio:', err);
          setError(err.message || 'Failed to load call audio.');
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedCallId]);

  async function loadCallData(id) {
    if (!id) return;
    const requestId = ++loadRequestId.current;
    setLoading(true);
    setError(null);
    setCurrentTime(0);
    setSeekTarget(null);
    setExpandAllDetails(null);
    setInteraction(null);
    setTimeline(null);
    setObservabilityData(null);
    setEvaluationRun(null);
    setReviews([]);
    try {
      const [interactionData, tlData, obsData, evalsData, revsData] =
        await Promise.all([
          api.getInteraction(id),
          api.getTimeline(id),
          api.getObservability(id),
          api.getEvaluations(id),
          api.listReviews(id),
        ]);

      if (requestId !== loadRequestId.current) return;
      setInteraction(interactionData);
      setTimeline(tlData);
      setObservabilityData(obsData);
      setEvaluationRun(evalsData);
      setReviews(revsData);
    } catch (err) {
      if (requestId !== loadRequestId.current) return;
      console.error('Error fetching interaction details:', err);
      setError(err.message || 'Failed to load interaction details');
    } finally {
      if (requestId === loadRequestId.current) setLoading(false);
    }
  }

  // Next / Previous navigation
  const currentIndex = callList.findIndex((c) => {
    const val = typeof c === 'string' ? c : c.interaction_id || c.id;
    return val === selectedCallId;
  });

  const handlePrevCall = () => {
    if (currentIndex > 0) {
      const prev = callList[currentIndex - 1];
      const val = typeof prev === 'string' ? prev : prev.interaction_id || prev.id;
      selectCallId(val);
    }
  };

  const handleNextCall = () => {
    if (currentIndex < callList.length - 1) {
      const next = callList[currentIndex + 1];
      const val = typeof next === 'string' ? next : next.interaction_id || next.id;
      selectCallId(val);
    }
  };

  const handleReevaluate = async (retryFailed = false) => {
    if (!selectedCallId) return;
    setEvaluating(true);
    try {
      const newRun = await api.evaluate(
        selectedCallId,
        retryFailed ? evaluationRun?.run_id : null
      );
      setEvaluationRun(newRun);
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
    if (!str) return 'Unavailable';
    if (str.toLowerCase() === 'none') return 'None';
    return str
      .toLowerCase()
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const turnRefs = useRef({});

  // Helper to seek to a given turn line number
  const seekToLine = (lineNum) => {
    if (!lineNum || !timeline?.events) return;
    const turnEvents = timeline.events.filter((e) => e.event_type === 'turn');
    const targetEvent =
      turnEvents.find((e) => e.metadata?.line === lineNum) ||
      turnEvents.find((e) => e.event_id === `turn_${lineNum - 1}`) ||
      turnEvents[lineNum - 1] ||
      timeline.events.find(
        (e) =>
          e.line === lineNum ||
          e.turn_index === lineNum - 1 ||
          e.metadata?.turn === lineNum - 1
      );
    if (targetEvent && typeof targetEvent.start_s === 'number') {
      setSeekTarget(targetEvent.start_s);
      const tid = targetEvent.event_id || `turn_${lineNum - 1}`;
      if (turnRefs.current[tid]) {
        turnRefs.current[tid].scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        });
      }
    }
  };

  // Filter & sort events for transcript chronologically
  const rawEvents = [...(timeline?.events || [])].sort((a, b) => {
    const aTime = a.start_s != null ? a.start_s : Infinity;
    const bTime = b.start_s != null ? b.start_s : Infinity;
    if (aTime !== bTime) return aTime - bTime;
    return (a.event_type === 'turn' ? 0 : 1) - (b.event_type === 'turn' ? 0 : 1);
  });
  const filteredEvents = rawEvents.filter((e) => {
    if (
      e.event_type === 'interruption' ||
      e.event_type === 'silence' ||
      e.event_type === 'booking' ||
      e.event_type === 'callback' ||
      e.event_type === 'appointment.booked' ||
      e.event_type === 'callback.scheduled'
    ) {
      return true;
    }
    if (speakerFilter !== 'all' && e.speaker !== speakerFilter) return false;

    if (deliveryFilter !== 'all') {
      const st = getDeliveryState(e).toLowerCase();
      if (deliveryFilter === 'cut' && st !== 'cut') return false;
      if (deliveryFilter === 'heard' && st !== 'heard') return false;
      if (deliveryFilter === 'not_played' && st !== 'not_played') return false;
      if (deliveryFilter === 'unknown' && st !== 'unknown') return false;
      if (deliveryFilter === 'mismatch' && st !== 'mismatch') return false;
    }

    if (turnSearch) {
      const q = turnSearch.toLowerCase();
      const txt = (e.text || '').toLowerCase();
      const norm = (e.metadata?.normalized_text || '').toLowerCase();
      if (!txt.includes(q) && !norm.includes(q)) return false;
    }
    return true;
  });

  // Derived evaluation data
  const evaluationBatches = evaluationRun?.batches || [];
  const understandingBatch = evaluationBatches.find(
    (batch) => batch.batch_name === 'conversation_understanding'
  );
  const qualityBatch = evaluationBatches.find(
    (batch) => batch.batch_name === 'conversation_quality'
  );
  const complianceBatch = evaluationBatches.find(
    (batch) => batch.batch_name === 'compliance_appointment'
  );

  const understanding = understandingBatch?.parsed_output;
  const quality = qualityBatch?.parsed_output;
  const compliance = complianceBatch?.parsed_output?.compliance?.rule_results;
  const appointmentInterpretation =
    complianceBatch?.parsed_output?.appointment_interpretation;

  const overallAssessment = evaluationRun?.summary?.overall_assessment;
  const conversationStatus =
    quality?.conversation_completeness?.conversation_status;
  const detectedRuleCount = Object.values(compliance || {}).filter(
    (rule) => rule.status === 'DETECTED'
  ).length;
  const criticalIssues = evaluationRun?.summary?.critical_issues || [];
  const hasFailedBatches = evaluationBatches.some((batch) => batch.status === 'failed');
  const whatHappened =
    evaluationRun?.summary?.what_happened || quality?.what_happened?.label;
  const firstThingWrongCategory =
    evaluationRun?.summary?.first_thing_wrong_category ||
    quality?.first_thing_wrong?.category ||
    quality?.first_thing_wrong_candidate?.category;
  const firstThingWrongLine =
    evaluationRun?.summary?.first_thing_wrong_line ??
    quality?.first_thing_wrong?.line ??
    quality?.first_thing_wrong_candidate?.line;
  const firstThingWrongDesc =
    evaluationRun?.summary?.first_thing_wrong_description ||
    quality?.first_thing_wrong?.description ||
    quality?.first_thing_wrong_candidate?.description;
  const firstThingWrongQuote =
    quality?.first_thing_wrong?.quote ||
    quality?.first_thing_wrong_candidate?.quote;

  const observabilityMetrics = observabilityData?.metrics;
  const formatMetric = (value, suffix = '') =>
    value == null ? 'Unavailable' : `${value}${suffix}`;

  const tabs = [
    { id: 'details', label: 'Details', icon: FileText },
    { id: 'observability', label: 'Observability', icon: Activity },
    { id: 'timeline', label: 'Timeline', icon: Clock },
    {
      id: 'evaluation',
      label: 'Evaluation',
      icon: Award,
      badge: detectedRuleCount > 0 ? `${detectedRuleCount} issues` : null,
      badgeColor: 'bg-rose-500 text-white',
    },
    {
      id: 'semantic_evaluation',
      label: 'Semantic Evaluation',
      icon: ShieldCheck,
      badge: evaluationBatches.length ? `${evaluationBatches.length}/3` : null,
      badgeColor: 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300',
    },
  ];

  const matchingActiveTurns = filteredEvents.filter((ev) => {
    if (ev.event_type !== 'turn' || ev.start_s == null) return false;
    const end =
      ev.end_s ??
      (typeof ev.start_s === 'number' && typeof ev.duration_s === 'number'
        ? ev.start_s + ev.duration_s
        : ev.start_s + 2);
    return currentTime >= ev.start_s && currentTime <= end;
  });

  // When speech intervals overlap, prioritize the most recently initiated turn so barge-in turns are highlighted
  const activeEvent =
    matchingActiveTurns.length > 0
      ? matchingActiveTurns.reduce((latest, curr) =>
          (curr.start_s || 0) > (latest.start_s || 0) ? curr : latest
        )
      : null;

  const activeTurnId = activeEvent?.event_id;

  // Auto-scroll transcript to active turn during playback
  useEffect(() => {
    if (activeTurnId && turnRefs.current[activeTurnId]) {
      turnRefs.current[activeTurnId].scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [activeTurnId]);

  return (
    <div className="h-full flex flex-col min-h-0 space-y-3">
      {/* 1. Top Hero Command Bar */}
      <div className="p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 shadow-sm shrink-0 space-y-2.5">
        {/* Top Controls Row: Selector on Left, Actions on Right */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-slate-800/80">
          {/* Interaction Dropdown & Steppers */}
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 font-medium">
              <FolderOpen className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
              <span className="hidden sm:inline">Call</span>
              <span>
                {currentIndex + 1} of {callList.length || 0}:
              </span>
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
                  selectCallId(id);
                }}
                className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-700 text-xs sm:text-sm font-sans text-cyan-800 dark:text-cyan-400 font-bold rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500 cursor-pointer max-w-[220px] sm:max-w-xs truncate"
              >
                {callList.map((c) => {
                  const val = typeof c === 'string' ? c : c.interaction_id || c.id;
                  const label =
                    typeof c === 'object' && (c.display_name || c.folder_name)
                      ? c.display_name || c.folder_name
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
                <RefreshCw
                  className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`}
                />
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => handleReevaluate(false)}
              disabled={evaluating || !selectedCallId}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border border-cyan-200 dark:bg-cyan-500/10 dark:hover:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 transition-all disabled:opacity-50 shadow-sm"
            >
              <Sparkles
                className={`w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400 ${
                  evaluating ? 'animate-spin' : ''
                }`}
              />
              <span>{evaluating ? 'Evaluating...' : 'Run evaluation'}</span>
            </button>

            {hasFailedBatches && (
              <button
                onClick={() => handleReevaluate(true)}
                disabled={evaluating}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 disabled:opacity-50"
              >
                Retry failed batches
              </button>
            )}

            <button
              onClick={() =>
                handleOpenAdjudicate(
                  evaluationBatches.find((batch) => batch.review_required) ||
                    evaluationBatches[0] ||
                    null
                )
              }
              disabled={!selectedCallId || evaluationBatches.length === 0}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors shadow-md shadow-cyan-500/20 disabled:opacity-50"
            >
              <UserCheck className="w-3.5 h-3.5" /> Adjudicate
            </button>
          </div>
        </div>

        {/* Executive Status Badges Strip */}
        <div className="flex flex-wrap items-center gap-2">
          {understanding?.outcome && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Outcome:</span>
              <span className="text-slate-900 dark:text-white font-bold">
                {understanding.outcome.label}
              </span>
            </div>
          )}

          {overallAssessment && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Assessment:</span>
              <span
                className={`font-bold ${
                  overallAssessment === 'Good'
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : overallAssessment === 'OK'
                    ? 'text-amber-600 dark:text-amber-400'
                    : 'text-rose-600 dark:text-rose-400'
                }`}
              >
                {overallAssessment}
              </span>
            </div>
          )}

          {understanding?.sentiment && understanding?.emotion && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Sentiment / emotion:</span>
              <span className="text-cyan-700 dark:text-cyan-300 font-bold">
                {understanding.sentiment.label} / {understanding.emotion.label}
              </span>
            </div>
          )}

          {conversationStatus && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans flex items-center gap-1.5 whitespace-nowrap shadow-sm">
              <span className="text-slate-500">Status:</span>
              <span className="font-bold text-slate-800 dark:text-slate-200">
                {conversationStatus}
              </span>
            </div>
          )}

          {firstThingWrongCategory && (
            <div
              className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm"
              title={firstThingWrongDesc || `Predicted failure: ${firstThingWrongCategory}`}
            >
              <span className="text-slate-500 mr-1.5">First failure:</span>
              <span
                className={`font-mono font-bold ${
                  firstThingWrongCategory === 'NONE'
                    ? 'text-emerald-700 dark:text-emerald-300'
                    : 'text-rose-700 dark:text-rose-300'
                }`}
              >
                {firstThingWrongCategory}
                {firstThingWrongLine != null ? ` (Line ${firstThingWrongLine})` : ''}
              </span>
            </div>
          )}

          {compliance && (
            <div className="px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs font-sans whitespace-nowrap shadow-sm">
              <span className="text-slate-500 mr-1.5">Detected compliance issues:</span>
              <span
                className={`font-bold ${
                  detectedRuleCount > 0
                    ? 'text-rose-700 dark:text-rose-300'
                    : 'text-emerald-700 dark:text-emerald-300'
                }`}
              >
                {detectedRuleCount} detected
              </span>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2 shrink-0">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. Main Two-Column Split Layout */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        {/* ========================================================================= */}
        {/* LEFT PANEL (5 cols): Audio Recording with Waveform on top + Transcript below */}
        {/* ========================================================================= */}
        <div className="lg:col-span-5 h-full overflow-y-auto pr-2 space-y-3">
          {/* Top of Left: Audio Player with Waveform Scrubber (Sticky) */}
          <div className="sticky top-0 z-20 bg-slate-50/95 dark:bg-[#060a12]/95 backdrop-blur-md pb-1 -mt-1 pt-1">
            <AudioPlayer
              audioUrl={audioUrl}
              currentTime={currentTime}
              onTimeUpdate={(t) => setCurrentTime(t)}
              onSeekTo={seekTarget}
              events={timeline?.events || []}
              totalDuration={timeline?.total_duration_s}
            />
          </div>

          {/* Bottom of Left: Transcript Stream Container */}
          <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 shadow-sm space-y-3">
            {/* Transcript Toolbar */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800/80 shrink-0">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                  Transcript
                </h3>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-semibold font-mono">
                  {filteredEvents.length} turns
                </span>
              </div>

              <button
                onClick={() =>
                  setExpandAllDetails(expandAllDetails === true ? false : true)
                }
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[11px] font-sans text-cyan-700 dark:text-cyan-400 border border-slate-200 dark:border-slate-700 transition-colors font-semibold shadow-sm"
                title="Toggle all turn inspector drawers"
              >
                {expandAllDetails === true ? (
                  <>
                    <ChevronUp className="w-3.5 h-3.5" /> Collapse All
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-3.5 h-3.5" /> Expand All
                  </>
                )}
              </button>
            </div>

            {/* Filters & Search */}
            <div className="space-y-2 shrink-0">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search in transcript..."
                  value={turnSearch}
                  onChange={(e) => setTurnSearch(e.target.value)}
                  className="w-full pl-8 pr-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 font-sans shadow-sm"
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-slate-400 font-medium mr-0.5">Speaker:</span>
                  {['all', 'agent', 'customer'].map((spk) => (
                    <button
                      key={spk}
                      onClick={() => setSpeakerFilter(spk)}
                      className={`px-2 py-0.5 rounded-md font-sans capitalize transition-all ${
                        speakerFilter === spk
                          ? 'bg-cyan-50 text-cyan-800 border border-cyan-300 dark:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 font-bold'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                      }`}
                    >
                      {spk}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-slate-400 font-medium mr-0.5">Evidence:</span>
                  {['all', 'heard', 'cut', 'mismatch'].map((st) => (
                    <button
                      key={st}
                      onClick={() => setDeliveryFilter(st)}
                      className={`px-2 py-0.5 rounded-md font-sans capitalize transition-all ${
                        deliveryFilter === st
                          ? 'bg-cyan-50 text-cyan-800 border border-cyan-300 dark:bg-cyan-500/20 dark:text-cyan-300 dark:border-cyan-500/40 font-bold'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Conversation Turns Stream (Natural height, no cramped inner scroll container) */}
            {filteredEvents.length === 0 ? (
              <div className="p-8 text-center rounded-xl border border-slate-200 dark:border-slate-800/80 bg-slate-50 dark:bg-slate-950/40 text-slate-500 text-xs">
                No matching conversation turns found for current filters.
              </div>
            ) : (
              <div className="space-y-2.5">
                {filteredEvents.map((ev, idx) => {
                  if (
                    ev.event_type === 'interruption' ||
                    ev.event_type === 'silence' ||
                    ev.event_type === 'booking' ||
                    ev.event_type === 'callback' ||
                    ev.event_type === 'appointment.booked' ||
                    ev.event_type === 'callback.scheduled'
                  ) {
                    return (
                      <TimelineMarker
                        key={ev.event_id || `marker_${idx}`}
                        event={ev}
                        onSeek={(s) => setSeekTarget(s)}
                      />
                    );
                  }

                  const start = ev.start_s;
                  const end =
                    ev.end_s ??
                    (typeof start === 'number' && typeof ev.duration_s === 'number'
                      ? start + ev.duration_s
                      : start != null
                      ? start + 2
                      : null);
                  const isActive =
                    start != null &&
                    end != null &&
                    currentTime >= start &&
                    currentTime <= end;

                  return (
                    <div
                      key={ev.event_id || `turn_${idx}`}
                      ref={(el) => {
                        const tid = ev.event_id || `turn_${idx}`;
                        if (el) turnRefs.current[tid] = el;
                      }}
                    >
                      <TimelineTurnCard
                        event={ev}
                        isActive={isActive}
                        onSeek={(s) => setSeekTarget(s)}
                        forceExpand={expandAllDetails}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* ========================================================================= */}
        {/* RIGHT PANEL (7 cols): Tabbed Results Deck                                 */}
        {/* Tabs: Details | Observability | Timeline | Evaluation | Semantic Evaluation*/}
        {/* ========================================================================= */}
        <div className="lg:col-span-7 h-full overflow-y-auto pr-2 flex flex-col space-y-3">
          {/* Tab Navigation Header Bar (Sticky) */}
          <div className="sticky top-0 z-20 bg-slate-50/95 dark:bg-[#060a12]/95 backdrop-blur-md pb-1 -mt-1 pt-1">
            <div className="p-1.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 shadow-sm dark:shadow-none flex items-center gap-1.5 overflow-x-auto">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap cursor-pointer ${
                      isActive
                        ? 'bg-cyan-500 text-slate-950 shadow-sm shadow-cyan-500/25'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/60'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    <span>{tab.label}</span>
                    {tab.badge && (
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                          isActive
                            ? 'bg-slate-950 text-cyan-300'
                            : tab.badgeColor
                        }`}
                      >
                        {tab.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Tab Content Container */}
          <div className="space-y-3.5">
            {/* Tab 1: Details (Overview, Canonical Info, Key Takeaways) */}
            {activeTab === 'details' && (
            <div className="space-y-4">
              {/* Canonical Interaction Info */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  <Info className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                  <span>Call Metadata & Canonical Details</span>
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800/80">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">
                      Status
                    </span>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {interaction?.status || 'Unavailable'}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800/80">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">
                      Use Case
                    </span>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {interaction?.use_case || 'Healthcare / Health Campaign'}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800/80">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">
                      Started At
                    </span>
                    <span className="font-bold text-slate-900 dark:text-slate-100">
                      {interaction?.started_at
                        ? new Date(interaction.started_at).toLocaleString()
                        : 'Unavailable'}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800/80">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">
                      Call ID / Folder
                    </span>
                    <span
                      className="font-mono text-[11px] font-bold text-cyan-700 dark:text-cyan-400 truncate block"
                      title={selectedCallId}
                    >
                      {selectedCallId}
                    </span>
                  </div>
                </div>
              </div>

              {/* Executive Summary Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-xs">
                {/* Outcome */}
                <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-slate-500">
                      Call Outcome
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full font-bold text-xs bg-cyan-50 dark:bg-cyan-500/10 text-cyan-800 dark:text-cyan-300 border border-cyan-200 dark:border-cyan-500/30">
                      {understanding?.outcome?.label || 'Unavailable'}
                    </span>
                  </div>
                  {understanding?.outcome?.reason && (
                    <p className="text-slate-600 dark:text-slate-300 text-xs">
                      {understanding.outcome.reason}
                    </p>
                  )}
                  {understanding?.outcome?.quote && (
                    <div
                      onClick={() => seekToLine(understanding.outcome.evidence_line)}
                      className="p-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 text-[11px] font-sans text-slate-700 dark:text-slate-300 cursor-pointer hover:border-cyan-500 transition-colors flex items-center justify-between"
                      title="Click to jump to audio line"
                    >
                      <span>
                        <strong className="text-cyan-600 dark:text-cyan-400 mr-1.5">
                          Line {understanding.outcome.evidence_line}:
                        </strong>
                        &ldquo;{understanding.outcome.quote}&rdquo;
                      </span>
                      <Play className="w-3 h-3 text-cyan-600 dark:text-cyan-400 shrink-0 ml-1" />
                    </div>
                  )}
                </div>

                {/* What Happened */}
                <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase text-slate-500">
                      What Happened
                    </span>
                    <span className="px-2.5 py-0.5 rounded-full font-bold text-xs bg-indigo-50 dark:bg-indigo-500/10 text-indigo-800 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/30">
                      {whatHappened || 'Unavailable'}
                    </span>
                  </div>
                  <p className="text-slate-600 dark:text-slate-300 text-xs">
                    {quality?.what_happened?.reason ||
                      'Standard call lifecycle observation.'}
                  </p>
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 pt-1">
                    <span>Overall:</span>
                    <strong
                      className={`${
                        overallAssessment === 'Good'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : overallAssessment === 'OK'
                          ? 'text-amber-600 dark:text-amber-400'
                          : 'text-rose-600 dark:text-rose-400'
                      }`}
                    >
                      {overallAssessment || 'Unavailable'}
                    </strong>
                    <span>&bull;</span>
                    <span>Status:</span>
                    <strong className="text-slate-700 dark:text-slate-200">
                      {conversationStatus || 'Unavailable'}
                    </strong>
                  </div>
                </div>
              </div>

              {/* First Thing Wrong Diagnostic Card */}
              {firstThingWrongCategory && firstThingWrongCategory !== 'NONE' && (
                <div className="p-4 rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/40 dark:bg-rose-950/20 shadow-sm space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400" />
                      <h4 className="text-xs font-bold uppercase tracking-wider text-rose-800 dark:text-rose-300">
                        First Failure Detected: {firstThingWrongCategory}
                      </h4>
                    </div>
                    {firstThingWrongLine != null && (
                      <span className="px-2 py-0.5 rounded-md font-mono text-xs bg-rose-100 dark:bg-rose-900/60 text-rose-800 dark:text-rose-200 font-bold">
                        Line {firstThingWrongLine}
                      </span>
                    )}
                  </div>
                  {firstThingWrongDesc && (
                    <p className="text-xs text-rose-900 dark:text-rose-200 leading-relaxed">
                      {firstThingWrongDesc}
                    </p>
                  )}
                  {firstThingWrongQuote && (
                    <div
                      onClick={() => seekToLine(firstThingWrongLine)}
                      className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-rose-200 dark:border-rose-900/50 text-xs text-slate-700 dark:text-slate-200 cursor-pointer hover:border-rose-400 flex items-center justify-between"
                      title="Click to jump audio to this failure point"
                    >
                      <span>
                        <strong>Evidence:</strong> &ldquo;{firstThingWrongQuote}&rdquo;
                      </span>
                      <Play className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400 ml-1 shrink-0" />
                    </div>
                  )}
                </div>
              )}

              {/* Extracted Customer Facts */}
              {understanding?.customer_facts &&
                understanding.customer_facts.length > 0 && (
                  <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-2.5">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                      <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      <span>Customer Facts Extracted ({understanding.customer_facts.length})</span>
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      {understanding.customer_facts.map((fact, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800"
                        >
                          <span className="text-[10px] uppercase font-bold text-cyan-700 dark:text-cyan-400 block">
                            {fact.fact_type || 'Customer Fact'}
                          </span>
                          <span className="font-semibold text-slate-800 dark:text-slate-200 block mt-0.5">
                            {fact.fact_value || JSON.stringify(fact)}
                          </span>
                          {fact.quote && (
                            <span className="text-[11px] text-slate-500 italic block mt-1">
                              &ldquo;{fact.quote}&rdquo;
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          )}

          {/* Tab 2: Observability (Technical Performance, Tokens, Costs) */}
          {activeTab === 'observability' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-1">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                    Technical observability
                  </h4>
                </div>
              </div>

              {!observabilityData?.available ? (
                <div className="p-8 text-center rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 text-xs text-slate-500">
                  Observability metrics are unavailable for this interaction.
                </div>
              ) : (
                <>
                  {/* Performance & Token Metrics Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        Recording Duration
                      </span>
                      <span className="text-base font-bold text-slate-900 dark:text-white mt-0.5 block">
                        {formatMetric(observabilityMetrics?.recording_duration_s, 's')}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        First Agent Latency
                      </span>
                      <span className="text-base font-bold text-cyan-600 dark:text-cyan-400 mt-0.5 block">
                        {formatMetric(observabilityMetrics?.first_agent_latency_s, 's')}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        Timestamp Quality
                      </span>
                      <span className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block capitalize">
                        {observabilityMetrics?.timestamp_quality || 'Good'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        Input Tokens
                      </span>
                      <span className="text-base font-bold text-slate-900 dark:text-white mt-0.5 block">
                        {observabilityMetrics?.input_tokens ?? 'Unavailable'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        Output Tokens
                      </span>
                      <span className="text-base font-bold text-slate-900 dark:text-white mt-0.5 block">
                        {observabilityMetrics?.output_tokens ?? 'Unavailable'}
                      </span>
                    </div>

                    <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                      <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                        Estimated Cost
                      </span>
                      <span className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block">
                        {observabilityMetrics?.cost_breakdown?.total_cost == null
                          ? 'Unavailable'
                          : `${observabilityMetrics.cost_breakdown.total_cost} ${
                              observabilityMetrics.cost_breakdown.currency || 'USD'
                            }`}
                      </span>
                    </div>
                  </div>

                  {/* Playback Delivery Audit Section */}
                  <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                      <Zap className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                      <span>Audio & Playback Delivery Audit</span>
                    </h4>
                    {observabilityMetrics?.playback_review_required ? (
                      <div className="p-3 rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/30 text-xs text-amber-800 dark:text-amber-300">
                        Playback metadata needs review.{' '}
                        {observabilityMetrics.playback_mismatches?.length || 0} mismatch(es)
                        detected between declared status and speech evidence.
                      </div>
                    ) : (
                      <div className="p-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/30 text-xs text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 shrink-0" />
                        <span>All audio playback delivery statuses matched expected turn evidence.</span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Tab 3: Timeline (Conversation Dynamics, Failures, Overlaps) */}
          {activeTab === 'timeline' && (
            <div className="space-y-4">
              {/* Timeline Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Total Duration
                  </span>
                  <span className="text-base font-bold text-slate-900 dark:text-white mt-0.5 block">
                    {timeline?.total_duration_s == null
                      ? 'Unavailable'
                      : `${timeline.total_duration_s.toFixed(1)}s`}
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Agent Turns
                  </span>
                  <span className="text-base font-bold text-cyan-600 dark:text-cyan-400 mt-0.5 block">
                    {timeline?.agent_turn_count ?? 0}
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Customer Turns
                  </span>
                  <span className="text-base font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block">
                    {timeline?.customer_turn_count ?? 0}
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Speech Overlaps
                  </span>
                  <span
                    className={`text-base font-bold mt-0.5 block ${
                      (timeline?.overlap_count || 0) > 0
                        ? 'text-amber-600 dark:text-amber-400'
                        : 'text-slate-800 dark:text-slate-200'
                    }`}
                  >
                    {timeline?.overlap_count ?? 0} (
                    {timeline?.total_overlap_s?.toFixed(1) || 0}s)
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Technical Failure
                  </span>
                  <span
                    className={`text-xs font-bold mt-1 block truncate ${
                      timeline?.first_technical_failure
                        ? 'text-rose-600 dark:text-rose-400'
                        : 'text-slate-600 dark:text-slate-400'
                    }`}
                  >
                    {formatFailureLabel(timeline?.first_technical_failure?.failure_type)}
                  </span>
                </div>

                <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm">
                  <span className="text-[10px] text-slate-500 uppercase block font-semibold">
                    Conversational Issue
                  </span>
                  <span
                    className={`text-xs font-bold mt-1 block truncate ${
                      timeline?.first_conversational_failure
                        ? 'text-rose-600 dark:text-rose-400'
                        : 'text-slate-600 dark:text-slate-400'
                    }`}
                  >
                    {formatFailureLabel(
                      timeline?.first_conversational_failure?.failure_type
                    )}
                  </span>
                </div>
              </div>

              {/* Detailed Failure Findings */}
              {(timeline?.first_technical_failure ||
                timeline?.first_conversational_failure) && (
                <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    <span>Timeline Failure Breakdown</span>
                  </h4>

                  {timeline.first_technical_failure && (
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-rose-600 dark:text-rose-400">
                          Technical: {timeline.first_technical_failure.failure_type}
                        </span>
                        {timeline.first_technical_failure.time_s != null && (
                          <span className="font-mono text-[11px] text-slate-500">
                            At {timeline.first_technical_failure.time_s.toFixed(1)}s
                          </span>
                        )}
                      </div>
                      {timeline.first_technical_failure.evidence && (
                        <p className="text-slate-600 dark:text-slate-300 text-[11px]">
                          {timeline.first_technical_failure.evidence}
                        </p>
                      )}
                    </div>
                  )}

                  {timeline.first_conversational_failure && (
                    <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-amber-600 dark:text-amber-400">
                          Conversational: {timeline.first_conversational_failure.failure_type}
                        </span>
                        {timeline.first_conversational_failure.turn_index != null && (
                          <span className="font-mono text-[11px] text-slate-500">
                            Turn {timeline.first_conversational_failure.turn_index + 1}
                          </span>
                        )}
                      </div>
                      {timeline.first_conversational_failure.evidence && (
                        <p className="text-slate-600 dark:text-slate-300 text-[11px]">
                          {timeline.first_conversational_failure.evidence}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Chronological Reconstructed Timeline Events Stream */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800/80">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                      Chronological Timeline Events
                    </h4>
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-semibold font-mono">
                      {(timeline?.events || []).length} events
                    </span>
                  </div>

                  <button
                    onClick={() =>
                      setExpandAllDetails(expandAllDetails === true ? false : true)
                    }
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[11px] font-sans text-cyan-700 dark:text-cyan-400 border border-slate-200 dark:border-slate-700 transition-colors font-semibold shadow-sm"
                  >
                    {expandAllDetails === true ? (
                      <>
                        <ChevronUp className="w-3.5 h-3.5" /> Collapse All
                      </>
                    ) : (
                      <>
                        <ChevronDown className="w-3.5 h-3.5" /> Expand All
                      </>
                    )}
                  </button>
                </div>

                {(!timeline?.events || timeline.events.length === 0) ? (
                  <div className="p-6 text-center text-xs text-slate-500">
                    No timeline events available for this call.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {timeline.events.map((ev, idx) => {
                      if (
                        ev.event_type === 'interruption' ||
                        ev.event_type === 'silence' ||
                        ev.event_type === 'booking' ||
                        ev.event_type === 'callback' ||
                        ev.event_type === 'appointment.booked' ||
                        ev.event_type === 'callback.scheduled'
                      ) {
                        return (
                          <TimelineMarker
                            key={ev.event_id || `tab_marker_${idx}`}
                            event={ev}
                            onSeek={(s) => setSeekTarget(s)}
                          />
                        );
                      }

                      const start = ev.start_s;
                      const end =
                        ev.end_s ??
                        (typeof start === 'number' && typeof ev.duration_s === 'number'
                          ? start + ev.duration_s
                          : start != null
                          ? start + 2
                          : null);
                      const isActive =
                        start != null &&
                        end != null &&
                        currentTime >= start &&
                        currentTime <= end;

                      return (
                        <TimelineTurnCard
                          key={ev.event_id || `tab_turn_${idx}`}
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
            </div>
          )}

          {/* Tab 4: Evaluation (Quality Dimensions Scorecard & Compliance) */}
          {activeTab === 'evaluation' && (
            <div className="space-y-4">
              {/* Quality Dimensions Scorecard */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                    <Award className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <span>Quality Dimensions Scorecard</span>
                  </h4>
                  {overallAssessment && (
                    <span
                      className={`px-2.5 py-0.5 rounded-full font-bold text-xs ${
                        overallAssessment === 'Good'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400'
                          : overallAssessment === 'OK'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950 dark:text-amber-400'
                          : 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950 dark:text-rose-400'
                      }`}
                    >
                      Overall: {overallAssessment}
                    </span>
                  )}
                </div>

                {quality?.conversation_quality?.dimensions ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                    {Object.entries(quality.conversation_quality.dimensions).map(
                      ([dimName, dimVal]) => (
                        <div
                          key={dimName}
                          className="p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800 space-y-1.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold capitalize text-slate-800 dark:text-slate-200">
                              {dimName.replace('_', ' ')}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                                dimVal.score >= 4
                                  ? 'bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-300'
                                  : dimVal.score === 3
                                  ? 'bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-300'
                                  : dimVal.score != null
                                  ? 'bg-rose-100 dark:bg-rose-900/50 text-rose-800 dark:text-rose-300'
                                  : 'bg-slate-200 dark:bg-slate-800 text-slate-600'
                              }`}
                            >
                              {dimVal.score != null ? `${dimVal.score}/5` : 'N/A'}
                            </span>
                          </div>
                          {dimVal.reason && (
                            <p className="text-[11px] text-slate-600 dark:text-slate-400">
                              {dimVal.reason}
                            </p>
                          )}
                          {dimVal.quote && (
                            <div
                              onClick={() => seekToLine(dimVal.evidence_line)}
                              className="text-[10px] text-cyan-700 dark:text-cyan-400 cursor-pointer hover:underline flex items-center gap-1"
                              title="Click to jump audio to this quote"
                            >
                              <Play className="w-2.5 h-2.5 shrink-0" />
                              <span>
                                Line {dimVal.evidence_line}: &ldquo;{dimVal.quote}&rdquo;
                              </span>
                            </div>
                          )}
                        </div>
                      )
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Quality dimensions not evaluated yet.</p>
                )}
              </div>

              {/* Compliance Checklist Audit */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <span>Compliance Rules (NR001 - NR006)</span>
                  </h4>
                  <span
                    className={`px-2.5 py-0.5 rounded-full font-bold text-xs ${
                      detectedRuleCount > 0
                        ? 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950 dark:text-rose-400'
                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400'
                    }`}
                  >
                    {detectedRuleCount} Detected
                  </span>
                </div>

                {compliance ? (
                  <div className="space-y-2 text-xs">
                    {Object.entries(compliance).map(([ruleCode, ruleData]) => {
                      const isViolation = ruleData.status === 'DETECTED';
                      return (
                        <div
                          key={ruleCode}
                          className={`p-3 rounded-xl border transition-colors ${
                            isViolation
                              ? 'bg-rose-50/50 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900/50'
                              : 'bg-slate-50 dark:bg-slate-950 border-slate-200/80 dark:border-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-slate-900 dark:text-slate-100">
                              {ruleCode}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                                isViolation
                                  ? 'bg-rose-600 text-white'
                                  : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                              }`}
                            >
                              {ruleData.status}
                            </span>
                          </div>
                          {ruleData.reason && (
                            <p className="text-slate-600 dark:text-slate-300 text-[11px] mb-1">
                              {ruleData.reason}
                            </p>
                          )}
                          {ruleData.quote && (
                            <div
                              onClick={() => seekToLine(ruleData.evidence_line)}
                              className="text-[10px] text-cyan-700 dark:text-cyan-400 cursor-pointer hover:underline flex items-center gap-1 font-sans"
                            >
                              <Play className="w-2.5 h-2.5 shrink-0" />
                              <span>
                                Line {ruleData.evidence_line}: &ldquo;{ruleData.quote}&rdquo;
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Compliance rules not evaluated yet.</p>
                )}
              </div>

              {/* Appointment Interpretation Card */}
              {appointmentInterpretation && (
                <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-2 text-xs">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <span>Appointment & Consent Interpretation</span>
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-1">
                    <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-[10px] text-slate-500 block uppercase">Type</span>
                      <strong className="text-slate-900 dark:text-slate-100">
                        {appointmentInterpretation.appointment_type || 'NONE'}
                      </strong>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-[10px] text-slate-500 block uppercase">Consent</span>
                      <strong className="text-slate-900 dark:text-slate-100">
                        {appointmentInterpretation.consent_status || 'NOT_PRESENT'}
                      </strong>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200/80 dark:border-slate-800">
                      <span className="text-[10px] text-slate-500 block uppercase">Agreed Time</span>
                      <strong className="text-slate-900 dark:text-slate-100">
                        {appointmentInterpretation.interpreted_date ||
                        appointmentInterpretation.interpreted_time
                          ? `${appointmentInterpretation.interpreted_date || ''} ${
                              appointmentInterpretation.interpreted_time || ''
                            }`
                          : 'None'}
                      </strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 5: Semantic Evaluation (3 Batches & Adjudication Audit Trail) */}
          {activeTab === 'semantic_evaluation' && (
            <div className="space-y-4">
              {/* Batch Cards */}
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs pb-1">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                    <h4 className="font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                      Semantic evaluation
                    </h4>
                  </div>
                  <span className="text-slate-500 font-semibold font-mono">
                    {evaluationBatches.length} of 3 completed
                  </span>
                </div>

                {evaluationBatches.length === 0 ? (
                  <div className="p-6 text-center rounded-2xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-900/30 text-slate-500 text-xs shadow-sm">
                    No evaluation run is available. Click &quot;Run evaluation&quot; in the top bar to run batches.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {evaluationBatches.map((ev) => (
                      <EvaluationCard
                        key={ev.evaluation_id}
                        evaluation={ev}
                        onOpenReview={handleOpenAdjudicate}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Human Adjudication Audit Trail */}
              <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/70 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <UserCheck className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
                    <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider font-sans">
                      Human Adjudication Audit Trail
                    </h4>
                  </div>
                  <button
                    onClick={() =>
                      handleOpenAdjudicate(
                        evaluationBatches.find((b) => b.review_required) ||
                          evaluationBatches[0] ||
                          null
                      )
                    }
                    disabled={!selectedCallId || evaluationBatches.length === 0}
                    className="text-xs font-sans text-cyan-600 hover:text-cyan-700 dark:text-cyan-400 dark:hover:text-cyan-300 font-semibold transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    + Add Review
                  </button>
                </div>

                {reviews.length === 0 ? (
                  <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800/60 bg-slate-50 dark:bg-slate-950/40 text-slate-500 text-xs font-sans">
                    No human adjudications logged yet. Adjudications will appear here as reviewers accept or override model verdicts.
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
                    {reviews.map((r, i) => (
                      <div
                        key={r.review_id || i}
                        className="p-3 rounded-xl bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-xs shadow-sm font-sans"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-mono text-cyan-700 dark:text-cyan-400 font-bold">
                            {r.evaluation_id || `Archived: ${r.evaluator_id}`}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                              r.review_decision === 'OVERRIDDEN'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-600/30'
                                : 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-600/30'
                            }`}
                          >
                            {r.review_decision}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-[11px] mb-1">
                          <span>
                            Label:{' '}
                            <strong className="text-slate-800 dark:text-slate-200">
                              {r.reviewed_label}
                            </strong>
                          </span>
                          <span>&bull;</span>
                          <span>
                            By:{' '}
                            <span className="text-slate-700 dark:text-slate-300">
                              {r.reviewer_name}
                            </span>
                          </span>
                        </div>
                        {r.notes && (
                          <p className="text-slate-600 dark:text-slate-300 text-[11px] italic">
                            &ldquo;{r.notes}&rdquo;
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
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
