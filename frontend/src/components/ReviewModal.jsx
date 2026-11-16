import React, { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, UserCheck } from 'lucide-react';
import { api } from '../api/client';

export default function ReviewModal({ isOpen, onClose, callId, evaluation, onSuccess }) {
  const [reviewedLabel, setReviewedLabel] = useState('');
  const [decision, setDecision] = useState('OVERRIDDEN');
  const [reviewerName, setReviewerName] = useState('Quality Lead');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setReviewedLabel('');
    setDecision('OVERRIDDEN');
    setReviewerName('Quality Lead');
    setNotes('');
    setError(null);
  }, [isOpen, callId, evaluation]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!callId?.trim() || !evaluation?.evaluation_id) {
      setError('Select an evaluation batch before submitting a review.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await api.submitReview(callId, {
        evaluation_id: evaluation.evaluation_id,
        reviewed_label: reviewedLabel,
        review_decision: decision,
        reviewer_name: reviewerName,
        notes,
      });
      if (onSuccess) onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to submit evaluation review:', err);
      setError(err.message || 'Failed to submit evaluation review');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl p-5 sm:p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-500/20">
              <UserCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Review evaluation batch</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-mono">
                Interaction: {callId} | {evaluation?.batch_name}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Review decision
              </label>
              <select
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200"
              >
                <option value="ACCEPTED">Accept result</option>
                <option value="OVERRIDDEN">Override result</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                Reviewed result
              </label>
              <input
                type="text"
                value={reviewedLabel}
                onChange={(e) => setReviewedLabel(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Reviewer name
            </label>
            <input
              type="text"
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Review notes
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-900 dark:text-slate-200 resize-none"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-xl text-xs font-semibold">
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !callId?.trim() || !evaluation?.evaluation_id}
              className="px-4 py-2 rounded-xl text-xs bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold flex items-center gap-1.5 disabled:opacity-50"
            >
              {loading ? 'Submitting...' : <><CheckCircle className="w-3.5 h-3.5" /> Submit review</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
