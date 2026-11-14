import React, { useState } from 'react';
import { AlertTriangle, CheckCircle, ChevronDown, ChevronUp, HelpCircle } from 'lucide-react';

function collectEvidence(value, path = [], evidence = []) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => collectEvidence(item, [...path, String(index)], evidence));
  } else if (value && typeof value === 'object') {
    const quoteFields = [
      ['quote', 'evidence_line'],
      ['customer_quote', 'customer_evidence_line'],
      ['agent_quote', 'agent_evidence_line'],
      ['consent_quote', 'consent_evidence_line'],
      ['agent_proposal_quote', 'agent_proposal_line'],
    ];
    for (const [quoteKey, lineKey] of quoteFields) {
      if (typeof value[quoteKey] === 'string' && value[quoteKey] && value[lineKey]) {
        evidence.push({
          line: value[lineKey],
          quote: value[quoteKey],
          reason: value.reason,
          field: path.join('.'),
        });
      }
    }

    for (const [key, child] of Object.entries(value)) {
      collectEvidence(child, [...path, key], evidence);
    }
  }
  return evidence;
}

export default function EvaluationCard({ evaluation, onOpenReview }) {
  const [expanded, setExpanded] = useState(false);
  const status = (evaluation.status || 'unknown').toUpperCase();
  const validation = evaluation.validation || {};
  const evidence = collectEvidence(evaluation.parsed_output);
  const statusIcon = status === 'COMPLETED'
    ? <CheckCircle className="w-3.5 h-3.5" />
    : status === 'FAILED'
      ? <AlertTriangle className="w-3.5 h-3.5" />
      : <HelpCircle className="w-3.5 h-3.5" />;
  const statusStyle = status === 'COMPLETED'
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/80 dark:text-emerald-400 dark:border-emerald-500/30'
    : status === 'FAILED'
      ? 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/80 dark:text-rose-400 dark:border-rose-500/30'
      : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/80 dark:text-amber-400 dark:border-amber-500/30';

  return (
    <article className={`p-4 rounded-2xl border shadow-sm dark:shadow-none ${
      status === 'FAILED' || evaluation.review_required
        ? 'bg-rose-50/40 dark:bg-rose-950/10 border-rose-200 dark:border-rose-900/40'
        : 'bg-white dark:bg-slate-900/50 border-slate-200 dark:border-slate-800/80'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {evaluation.batch_name.replace(/_/g, ' ')}
          </h4>
          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 font-mono">
            Model: {evaluation.model} | Schema {evaluation.schema_version} | Prompt {evaluation.prompt_version}
          </p>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${statusStyle}`}>
          {statusIcon} {status}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
        <span className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
          Review: {evaluation.review_status}
        </span>
        <span className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
          Schema: {validation.schema_valid ? 'Valid' : 'Invalid'}
        </span>
        <span className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
          Evidence: {validation.evidence_valid ? 'Valid' : 'Invalid'}
        </span>
      </div>

      {evaluation.error_message && (
        <p className="mt-3 p-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/50 text-xs text-rose-700 dark:text-rose-300">
          {evaluation.error_type}: {evaluation.error_message}
        </p>
      )}

      {evaluation.review_reasons?.length > 0 && (
        <ul className="mt-3 list-disc list-inside space-y-1 text-xs text-amber-800 dark:text-amber-300">
          {evaluation.review_reasons.map((reason, index) => <li key={index}>{reason}</li>)}
        </ul>
      )}

      {evaluation.parsed_output && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-600 dark:text-slate-300">
            Structured result
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-50 dark:bg-slate-950 p-3 text-[11px] text-slate-700 dark:text-slate-300">
            {JSON.stringify(evaluation.parsed_output, null, 2)}
          </pre>
        </details>
      )}

      {evidence.length > 0 && (
        <div className="mt-3 border-t border-slate-200 dark:border-slate-800 pt-3">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs font-semibold text-cyan-700 dark:text-cyan-400"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? 'Hide exact transcript evidence' : `View ${evidence.length} exact transcript quote(s)`}
          </button>
          {expanded && (
            <div className="mt-2 space-y-2">
              {evidence.map((item, index) => (
                <blockquote
                  key={`${item.line}-${index}`}
                  className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-3"
                >
                  <p className="text-[10px] font-mono text-slate-500">
                    Line {item.line}{item.field ? ` · ${item.field}` : ''}
                  </p>
                  <p className="mt-1 text-xs italic text-slate-800 dark:text-slate-200">
                    "{item.quote}"
                  </p>
                  {item.reason && <p className="mt-1 text-[11px] text-slate-500">{item.reason}</p>}
                </blockquote>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/40 flex justify-end">
        <button
          type="button"
          onClick={() => onOpenReview?.(evaluation)}
          disabled={!evaluation.evaluation_id}
          className="text-xs font-medium text-slate-500 hover:text-cyan-600 dark:text-slate-400 dark:hover:text-cyan-400 disabled:opacity-40"
        >
          Review batch
        </button>
      </div>
    </article>
  );
}
