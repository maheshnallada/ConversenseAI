import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import ConfusionMatrix from '../components/ConfusionMatrix';
import { AlertTriangle, Award, FileText, RefreshCw, UploadCloud } from 'lucide-react';

function AvailabilityCard({ title, status }) {
  const available = status === 'available';
  return (
    <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{title}</p>
      <p className={`mt-2 text-sm font-bold ${available ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
        {available ? 'Available' : 'Unavailable'}
      </p>
    </div>
  );
}

export default function BenchmarkView() {
  const [benchmark, setBenchmark] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadBenchmark();
  }, []);

  async function loadBenchmark() {
    setLoading(true);
    setError(null);
    try {
      setBenchmark(await api.getBenchmark());
    } catch (err) {
      console.error('Failed to load benchmark:', err);
      setError(err.message || 'Failed to load golden benchmark.');
    } finally {
      setLoading(false);
    }
  }

  async function handleImportGolden() {
    setImporting(true);
    setError(null);
    try {
      const result = await api.importGolden();
      setImportResult(result);
      setBenchmark(result.report);
    } catch (err) {
      console.error('Failed to import golden dataset:', err);
      setError(err.message || 'Failed to import golden dataset.');
    } finally {
      setImporting(false);
    }
  }

  const dimensions = benchmark?.dimension_metrics
    ? Object.entries(benchmark.dimension_metrics)
    : [];
  const languageSlices = benchmark?.details?.language_slice_metrics || {};

  return (
    <div className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/20 flex items-center justify-center text-cyan-600 dark:text-cyan-400">
            <Award className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Golden dataset benchmark
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Dimension metrics compare labels with evaluations of the dataset's outcome-free input.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleImportGolden}
            disabled={importing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 disabled:opacity-50"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            {importing ? 'Importing...' : 'Import golden CSV'}
          </button>
          <button
            type="button"
            onClick={loadBenchmark}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {importResult && (
        <>
          <section className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
              Latest import processing
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                ['Records seen', importResult.records_seen],
                ['Labels imported', importResult.labels_imported],
                ['Tests excluded', importResult.test_records_excluded],
                ['Evaluations created', importResult.evaluations_created],
                ['Evaluations reused', importResult.evaluations_reused],
                ['Evaluations failed', importResult.evaluations_failed],
              ].map(([label, count]) => (
                <div key={label} className="p-3 rounded-xl bg-slate-50 dark:bg-slate-800/70">
                  <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                    {label}
                  </p>
                  <p className="mt-1 text-lg font-bold font-mono text-slate-900 dark:text-white">
                    {count}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {importResult.records?.some((record) => record.error) && (
            <section
              aria-live="polite"
              className="p-4 sm:p-5 rounded-2xl border border-rose-200 dark:border-rose-800 bg-rose-50 dark:bg-rose-950/30"
            >
              <h3 className="text-sm font-bold text-rose-800 dark:text-rose-300 mb-3">
                Per-record processing errors
              </h3>
              <ul className="space-y-2">
                {importResult.records
                  .filter((record) => record.error)
                  .map((record) => (
                    <li
                      key={record.call_id}
                      className="text-xs text-rose-700 dark:text-rose-300"
                    >
                      <span className="font-semibold">{record.call_id}:</span>{' '}
                      {record.error}
                    </li>
                  ))}
              </ul>
            </section>
          )}
        </>
      )}

      {loading && !benchmark ? (
        <p className="p-8 text-center text-sm text-slate-500">Loading benchmark data...</p>
      ) : !benchmark || benchmark.total_interactions === 0 ? (
        <p className="p-8 text-center text-sm text-slate-500">No golden benchmark data is available.</p>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
              <p className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <FileText className="w-4 h-4 text-cyan-600" /> Golden interactions
              </p>
              <p className="mt-2 text-2xl font-bold font-mono text-slate-900 dark:text-white">
                {benchmark.total_interactions}
              </p>
            </div>
            <AvailabilityCard
              title="Conversation completeness labels"
              status={benchmark.details?.availability?.conversation_status}
            />
            <AvailabilityCard
              title="Language-slice labels"
              status={benchmark.details?.availability?.language_slice}
            />
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
              <p className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <AlertTriangle className="w-4 h-4 text-rose-600" /> Compliance false negatives
              </p>
              <p className="mt-2 text-2xl font-bold font-mono text-rose-600 dark:text-rose-400">
                {benchmark.compliance_false_negatives}
              </p>
            </div>
          </div>

          <section className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
              Dimension metrics
            </h3>
            {dimensions.length === 0 ? (
              <p className="text-xs text-slate-500">No labeled dimensions are available.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono border-collapse min-w-[500px]">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 text-left">
                      <th className="py-2.5 px-3">Dimension</th>
                      <th className="py-2.5 px-3">Accuracy</th>
                      <th className="py-2.5 px-3">Precision</th>
                      <th className="py-2.5 px-3">Recall</th>
                      <th className="py-2.5 px-3">Macro F1</th>
                      <th className="py-2.5 px-3">Support</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                    {dimensions.map(([dimension, scores]) => (
                      <tr key={dimension}>
                        <td className="py-2.5 px-3 font-semibold text-slate-800 dark:text-slate-200">
                          {dimension.replace(/_/g, ' ')}
                        </td>
                        <td className="py-2.5 px-3">{(scores.accuracy * 100).toFixed(1)}%</td>
                        <td className="py-2.5 px-3">{scores.precision.toFixed(3)}</td>
                        <td className="py-2.5 px-3">{scores.recall.toFixed(3)}</td>
                        <td className="py-2.5 px-3">{scores.f1_score.toFixed(3)}</td>
                        <td className="py-2.5 px-3">{scores.support}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {Object.keys(languageSlices).length > 0 && (
            <section className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
                Explicit language-slice metrics
              </h3>
              <div className="space-y-4">
                {Object.entries(languageSlices).map(([languageSlice, metrics]) => (
                  <div key={languageSlice}>
                    <h4 className="text-xs font-bold text-cyan-700 dark:text-cyan-400 mb-2">
                      {languageSlice}
                    </h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(metrics).map(([dimension, scores]) => (
                        <span
                          key={dimension}
                          className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-[11px] text-slate-700 dark:text-slate-300"
                        >
                          {dimension.replace(/_/g, ' ')}: {(scores.accuracy * 100).toFixed(1)}% (n={scores.support})
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {benchmark.confusion_matrices && Object.keys(benchmark.confusion_matrices).length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {Object.entries(benchmark.confusion_matrices).map(([key, data]) => (
                <ConfusionMatrix
                  key={key}
                  title={`Confusion Matrix: ${key.replace(/_/g, ' ').toUpperCase()}`}
                  matrixData={data}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
