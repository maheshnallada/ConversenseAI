import React, { useState } from 'react';
import { ShieldCheck, AlertTriangle, XCircle, HelpCircle, ChevronDown, ChevronUp, UserCheck } from 'lucide-react';

export default function EvaluationCard({ evaluation, onOpenReview, onSeek }) {
  const [expanded, setExpanded] = useState(false);

  const status = (evaluation.review_status || 'PASSED').toUpperCase();
  const score = evaluation.score !== null && evaluation.score !== undefined ? evaluation.score : null;
  const confidence = evaluation.confidence !== null && evaluation.confidence !== undefined ? evaluation.confidence : null;

  const getStatusBadge = () => {
    if (status === 'PASSED') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-400 dark:border-emerald-500/30">
          <ShieldCheck className="w-3.5 h-3.5" /> PASSED
        </span>
      );
    }
    if (status === 'FLAGGED_FOR_REVIEW') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/80 dark:text-rose-400 dark:border-rose-500/40 animate-pulse">
          <AlertTriangle className="w-3.5 h-3.5" /> FLAGGED
        </span>
      );
    }
    if (status === 'FAILED') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300 dark:bg-rose-950 dark:text-rose-400 dark:border-rose-600">
          <XCircle className="w-3.5 h-3.5" /> FAILED
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/80 dark:text-amber-400 dark:border-amber-500/30">
        <HelpCircle className="w-3.5 h-3.5" /> {status}
      </span>
    );
  };

  const getFamilyBadge = (fam) => {
    return (
      <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700/60 font-semibold">
        {fam || 'general'}
      </span>
    );
  };

  return (
    <div className={`p-4 rounded-2xl border transition-all shadow-sm dark:shadow-none ${
      status === 'FLAGGED_FOR_REVIEW' || status === 'FAILED'
        ? 'bg-rose-50/40 dark:bg-rose-950/10 border-rose-200 dark:border-rose-900/40 hover:border-rose-300 dark:hover:border-rose-700/60'
        : 'bg-white dark:bg-slate-900/50 border-slate-200 dark:border-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700'
    }`}>
      {/* Top Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 font-mono tracking-tight">
              {evaluation.evaluator_id}
            </h4>
            {getFamilyBadge(evaluation.family)}
            {evaluation.method && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-50 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-800/30 font-semibold">
                {evaluation.method}
              </span>
            )}
          </div>
          {evaluation.label && (
            <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">
              Label: <span className="text-slate-800 dark:text-slate-200 font-semibold">{evaluation.label}</span>
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {getStatusBadge()}
        </div>
      </div>

      {/* Score & Confidence Metric row */}
      <div className="flex items-center gap-4 mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/60 text-xs">
        {score !== null && (
          <div className="flex items-center gap-1.5 font-mono">
            <span className="text-slate-500">Score:</span>
            <span className={`font-semibold ${score >= 0.8 ? 'text-emerald-600 dark:text-emerald-400' : score >= 0.5 ? 'text-amber-600 dark:text-amber-400' : 'text-rose-600 dark:text-rose-400'}`}>
              {(score * 100).toFixed(0)}%
            </span>
          </div>
        )}
        {confidence !== null && (
          <div className="flex items-center gap-1.5 font-mono">
            <span className="text-slate-500">Confidence:</span>
            <span className="text-cyan-600 dark:text-cyan-400 font-semibold">{(confidence * 100).toFixed(0)}%</span>
          </div>
        )}
        {evaluation.severity && (
          <div className="flex items-center gap-1.5 font-mono">
            <span className="text-slate-500">Severity:</span>
            <span className="text-slate-700 dark:text-slate-300 capitalize font-medium">{evaluation.severity}</span>
          </div>
        )}
      </div>

      {/* Reason / Explanation */}
      {evaluation.reason && (
        <p className="mt-2.5 text-xs text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-950/50 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800/60 font-sans">
          {evaluation.reason}
        </p>
      )}

      {/* Quoted Evidence toggle */}
      {evaluation.evidence && evaluation.evidence.length > 0 && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-cyan-600 dark:text-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300 font-mono transition-colors font-medium"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? 'Hide Evidence Snippets' : `View ${evaluation.evidence.length} Evidence Snippet(s)`}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2">
              {evaluation.evidence.map((ev, i) => (
                <div key={i} className="p-2.5 rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 text-xs font-mono shadow-sm dark:shadow-none">
                  {ev.timestamp_s !== null && ev.timestamp_s !== undefined && (
                    <button
                      type="button"
                      onClick={() => onSeek && onSeek(ev.timestamp_s)}
                      className="inline-flex items-center gap-1 text-[10px] text-cyan-700 dark:text-cyan-400 bg-cyan-100/70 hover:bg-cyan-200 dark:bg-cyan-950/70 dark:hover:bg-cyan-900 px-2 py-0.5 rounded border border-cyan-300 dark:border-cyan-800/50 mr-2 transition-colors cursor-pointer group font-semibold"
                      title="Jump audio to this evidence"
                    >
                      <span>@ {ev.timestamp_s.toFixed(1)}s</span>
                      <span className="text-[9px] group-hover:translate-x-0.5 transition-transform">&rarr;</span>
                    </button>
                  )}
                  {ev.source_type && (
                    <span className="text-[10px] text-slate-500 mr-2 uppercase">
                      [{ev.source_type}]
                    </span>
                  )}
                  {ev.text_snippet && (
                    <p className="text-slate-800 dark:text-slate-200 mt-1 italic font-sans">
                      &ldquo;{ev.text_snippet}&rdquo;
                    </p>
                  )}
                  {ev.reason && (
                    <p className="text-slate-500 dark:text-slate-400 mt-1 text-[11px] font-sans">
                      {ev.reason}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Adjudication Trigger */}
      <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/40 flex justify-end">
        <button
          onClick={() => onOpenReview && onOpenReview(evaluation)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-cyan-600 dark:text-slate-400 dark:hover:text-cyan-400 transition-colors"
        >
          <UserCheck className="w-3.5 h-3.5" /> Adjudicate / Review
        </button>
      </div>
    </div>
  );
}
