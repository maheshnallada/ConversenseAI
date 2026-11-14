import React, { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, UserCheck } from 'lucide-react';
import { api } from '../api/client';

export default function ReviewModal({ isOpen, onClose, callId, evaluation, onSuccess }) {
  const [evaluatorId, setEvaluatorId] = useState(evaluation?.evaluator_id || 'safety');
  const [reviewedLabel, setReviewedLabel] = useState(evaluation?.label || 'PASSED');
  const [decision, setDecision] = useState('OVERRIDDEN');
  const [reviewerName, setReviewerName] = useState('Quality Lead');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setEvaluatorId(evaluation?.evaluator_id || 'safety');
    setReviewedLabel(evaluation?.label || 'PASSED');
    setDecision('OVERRIDDEN');
    setReviewerName('Quality Lead');
    setNotes('');
    setError(null);
  }, [isOpen, callId, evaluation]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!callId?.trim()) {
      setError('Select an interaction before submitting an adjudication.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await api.submitReview(callId, {
        evaluator_id: evaluatorId,
        reviewed_label: reviewedLabel,
        review_decision: decision,
        original_label: evaluation?.label || evaluation?.review_status || 'UNKNOWN',
        reviewer_name: reviewerName,
        notes: notes,
      });
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to submit adjudication:', err);
      setError(err.message || 'Failed to submit adjudication review');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl p-5 sm:p-6 transition-colors">
        <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-500/20">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Adjudicate Evaluation</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">Interaction: {callId}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-xs font-mono font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Target Evaluator
            </label>
            <input
              type="text"
              value={evaluatorId}
              onChange={(e) => setEvaluatorId(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm font-mono text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-mono font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Review Decision
              </label>
              <select
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 font-sans"
              >
                <option value="ACCEPTED">ACCEPTED (Confirm)</option>
                <option value="OVERRIDDEN">OVERRIDDEN (Change)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-mono font-semibold text-slate-600 dark:text-slate-400 mb-1">
                New Adjudicated Label
              </label>
              <input
                type="text"
                value={reviewedLabel}
                onChange={(e) => setReviewedLabel(e.target.value)}
                required
                placeholder="e.g. PASSED or FLAGGED"
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 font-sans"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-mono font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Reviewer Name
            </label>
            <input
              type="text"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 font-sans"
            />
          </div>

          <div>
            <label className="block text-xs font-mono font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Clinical / Quality Rationale
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Explain the clinical adjudication or why the automated evaluator was accepted/overridden..."
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200 focus:outline-none focus:border-cyan-500 resize-none font-sans"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !callId?.trim()}
              className="px-4 py-2 rounded-xl text-xs bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold shadow-md shadow-cyan-500/20 transition-all flex items-center gap-1.5 disabled:opacity-50"
            >
              {loading ? (
                <span>Submitting...</span>
              ) : (
                <>
                  <CheckCircle className="w-3.5 h-3.5" /> Submit Adjudication
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
