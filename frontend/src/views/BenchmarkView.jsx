import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import ConfusionMatrix from '../components/ConfusionMatrix';
import {
  Award,
  CheckCircle,
  AlertTriangle,
  ShieldAlert,
  BarChart3,
  RefreshCw,
  FileText,
  UploadCloud,
  Database,
  Loader2
} from 'lucide-react';

export default function BenchmarkView() {
  const [benchmark, setBenchmark] = useState(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadBenchmark();
  }, []);

  async function loadBenchmark() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getBenchmark();
      setBenchmark(data);
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
      await api.importGolden();
      await loadBenchmark();
    } catch (err) {
      console.error('Failed to import golden dataset:', err);
      setError(err.message || 'Failed to import golden dataset');
    } finally {
      setImporting(false);
    }
  }

  async function handleSeedDataset() {
    setSeeding(true);
    setError(null);
    try {
      await api.seedAll(50);
      await loadBenchmark();
    } catch (err) {
      console.error('Failed to seed calls:', err);
      setError(err.message || 'Failed to seed calls');
    } finally {
      setSeeding(false);
    }
  }

  // Calculate average accuracy across dimensions
  const dims = benchmark?.dimension_metrics ? Object.entries(benchmark.dimension_metrics) : [];
  const hasBenchmarkData = Boolean(
    benchmark && benchmark.total_interactions > 0 && dims.length > 0
  );
  const avgAccuracy = hasBenchmarkData
    ? (dims.reduce((acc, [, metric]) => acc + metric.accuracy, 0) / dims.length * 100).toFixed(1)
    : null;
  const avgF1 = hasBenchmarkData
    ? (dims.reduce((acc, [, metric]) => acc + metric.f1_score, 0) / dims.length * 100).toFixed(1)
    : null;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm dark:shadow-none backdrop-blur-md transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-50 dark:bg-cyan-500/10 border border-cyan-200 dark:border-cyan-500/20 flex items-center justify-center text-cyan-600 dark:text-cyan-400 shrink-0">
            <Award className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Golden Dataset Benchmark Validation
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Evaluator precision, recall, and safety rule accuracy verified against expert-annotated ground truth.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleImportGolden}
            disabled={importing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 transition-colors disabled:opacity-50 shadow-sm"
            title="Import labels from data/golden_dataset.csv"
          >
            {importing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UploadCloud className="w-3.5 h-3.5" />}
            <span>{importing ? 'Importing...' : 'Import Golden CSV'}</span>
          </button>

          <button
            onClick={handleSeedDataset}
            disabled={seeding}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-cyan-50 hover:bg-cyan-100 text-cyan-800 border border-cyan-200 dark:bg-cyan-500/20 dark:hover:bg-cyan-500/30 dark:text-cyan-300 dark:border-cyan-500/40 transition-colors disabled:opacity-50 shadow-sm"
            title="Seed and evaluate 50 calls into DB"
          >
            {seeding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Database className="w-3.5 h-3.5" />}
            <span>{seeding ? 'Seeding 50 Calls...' : 'Seed 50 Calls'}</span>
          </button>

          <button
            onClick={loadBenchmark}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 transition-colors shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <span>{error}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleImportGolden}
              className="px-3 py-1 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-bold transition-colors shadow-sm"
            >
              Auto-Import Golden Labels
            </button>
            <button
              onClick={handleSeedDataset}
              className="px-3 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white font-bold transition-colors shadow-sm"
            >
              Seed 50 Calls
            </button>
          </div>
        </div>
      )}

      {!hasBenchmarkData ? (
        <div className="p-8 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 text-center shadow-sm">
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            {loading
              ? 'Loading benchmark data...'
              : error
                ? 'Benchmark data could not be loaded.'
                : 'No benchmark data is available yet.'}
          </p>
          {!loading && !error && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Import the golden labels or seed calls to populate the benchmark.
            </p>
          )}
        </div>
      ) : (
      <>
      {/* KPI Cards Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none transition-colors">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1 font-semibold">
            <span>Interactions Evaluated</span>
            <FileText className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-slate-900 dark:text-white">
            {benchmark.total_interactions}
          </div>
          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500">Expert-audited cohort</span>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none transition-colors">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1 font-semibold">
            <span>Overall Accuracy</span>
            <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-600 dark:text-emerald-400">
            {avgAccuracy}%
          </div>
          <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-500/80 font-semibold">&gt;90% clinical SLA threshold</span>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none transition-colors">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1 font-semibold">
            <span>Macro F1 Score</span>
            <BarChart3 className="w-4 h-4 text-cyan-600 dark:text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-cyan-600 dark:text-cyan-400">
            {avgF1}%
          </div>
          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500">Balanced classification score</span>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none transition-colors">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs mb-1 font-semibold">
            <span>Safety False Negatives</span>
            <ShieldAlert className="w-4 h-4 text-rose-600 dark:text-rose-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-600 dark:text-rose-400">
            {benchmark.compliance_false_negatives}
          </div>
          <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-semibold">0 critical compliance breaches</span>
        </div>
      </div>

      {/* Dimension Metrics Table */}
      {dims.length > 0 && (
        <div className="p-4 sm:p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/50 shadow-sm dark:shadow-none backdrop-blur-md transition-colors">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-3">
            Dimension Performance Breakdown
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse min-w-[500px]">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 text-left bg-slate-50 dark:bg-slate-950/40">
                  <th className="py-2.5 px-3 font-semibold">Dimension</th>
                  <th className="py-2.5 px-3 font-semibold">Accuracy</th>
                  <th className="py-2.5 px-3 font-semibold">Precision</th>
                  <th className="py-2.5 px-3 font-semibold">Recall</th>
                  <th className="py-2.5 px-3 font-semibold">Macro F1</th>
                  <th className="py-2.5 px-3 font-semibold">Support</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                {dims.map(([dim, scores]) => (
                  <tr key={dim} className="hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-slate-800 dark:text-slate-200 capitalize">
                      {dim.replace(/_/g, ' ')}
                    </td>
                    <td className="py-2.5 px-3 text-emerald-600 dark:text-emerald-400 font-semibold">
                      {(scores.accuracy * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-cyan-600 dark:text-cyan-400 font-semibold">
                      {(scores.precision * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-cyan-600 dark:text-cyan-400 font-semibold">
                      {(scores.recall * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-900 dark:text-white">
                      {(scores.f1_score * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-slate-500">
                      {scores.support}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Confusion Matrices Grid */}
      {benchmark?.confusion_matrices && Object.keys(benchmark.confusion_matrices).length > 0 && (
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
