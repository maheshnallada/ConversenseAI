import React, { useState, useRef } from 'react';
import { api } from '../api/client';
import {
  UploadCloud,
  FolderOpen,
  FileCheck,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Database,
  Sparkles,
  Layers,
  ShieldCheck,
  Clock,
  Loader2
} from 'lucide-react';

export default function IngestView({ onNavigateToDrillDown }) {
  const [activeTab, setActiveTab] = useState('path'); // 'path' or 'upload' or 'seed'

  // Server path state
  const [folderPath, setFolderPath] = useState('data/calls/call_01');

  // ZIP upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  // Status & Results
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState('');
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Quick selection chips
  const quickPaths = [
    'data/calls/call_01',
    'data/calls/call_18',
    'data/calls/call_05',
    'data/calls/call_12',
    'data/calls/call_33',
  ];

  const handleFileDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.name.endsWith('.zip')) {
        setSelectedFile(file);
        setError(null);
      } else {
        setError('Please drop a valid .zip archive containing call.json and artifacts.');
      }
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setError(null);
    }
  };

  const handleProcessPath = async (e) => {
    if (e) e.preventDefault();
    if (!folderPath.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setCurrentStep('Locating folder & reconciling timestamps...');

    try {
      setTimeout(() => setCurrentStep('Reconstructing chronological timeline & audio markers...'), 400);
      setTimeout(() => setCurrentStep('Executing multi-dimensional evaluators suite...'), 1000);

      const resp = await api.processPath(folderPath.trim());
      setResult(resp);
    } catch (err) {
      console.error('Process path error:', err);
      setError(err.message || 'Failed to process folder path.');
    } finally {
      setLoading(false);
      setCurrentStep('');
    }
  };

  const handleUploadZip = async (e) => {
    if (e) e.preventDefault();
    if (!selectedFile) return;

    setLoading(true);
    setError(null);
    setResult(null);
    setCurrentStep('Uploading ZIP archive to staging area...');

    try {
      setTimeout(() => setCurrentStep('Unpacking and reconciling transcripts & audio...'), 600);
      setTimeout(() => setCurrentStep('Running evaluators on extracted conversation...'), 1400);

      const resp = await api.uploadZip(selectedFile);
      setResult(resp.report || resp);
    } catch (err) {
      console.error('Upload zip error:', err);
      setError(err.message || 'Failed to upload and ingest archive.');
    } finally {
      setLoading(false);
      setCurrentStep('');
    }
  };

  const handleBatchSeed = async (limit = 10) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setCurrentStep(`Seeding first ${limit} dataset calls into observability database...`);

    try {
      const resp = await api.seedAll(limit);
      alert(`Seeding complete! Processed ${resp.processed} calls with ${resp.errors} errors.`);
    } catch (err) {
      console.error('Seed error:', err);
      setError(err.message || 'Failed to seed dataset.');
    } finally {
      setLoading(false);
      setCurrentStep('');
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header Banner */}
      <div className="p-6 rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900/90 via-slate-900/70 to-slate-950/90 backdrop-blur-md">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <UploadCloud className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">On-Demand Call Ingestion &amp; Evaluation</h2>
            <p className="text-xs text-slate-400">
              Ingest raw audio &amp; JSON call telemetry, reconstruct chronological timeline with latency compensation, and execute evaluation policies.
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 mt-5 border-b border-slate-800/80 pb-2">
          <button
            onClick={() => { setActiveTab('path'); setError(null); }}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all flex items-center gap-2 ${
              activeTab === 'path'
                ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-700 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
          >
            <FolderOpen className="w-4 h-4" /> Server Folder Path
          </button>
          <button
            onClick={() => { setActiveTab('upload'); setError(null); }}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all flex items-center gap-2 ${
              activeTab === 'upload'
                ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-700 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
          >
            <UploadCloud className="w-4 h-4" /> Upload ZIP Archive
          </button>
          <button
            onClick={() => { setActiveTab('seed'); setError(null); }}
            className={`px-4 py-2 rounded-lg text-xs font-medium transition-all flex items-center gap-2 ${
              activeTab === 'seed'
                ? 'bg-slate-800 text-cyan-400 shadow-sm border border-slate-700 font-semibold'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/40'
            }`}
          >
            <Database className="w-4 h-4" /> Batch Dataset Seeder
          </button>
        </div>
      </div>

      {/* Main Action Card */}
      <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/50 backdrop-blur-md">
        {/* Tab 1: Server Folder Path */}
        {activeTab === 'path' && (
          <form onSubmit={handleProcessPath} className="space-y-5">
            <div>
              <label className="block text-xs font-mono text-slate-300 uppercase tracking-wider mb-2">
                Server Folder Path (Relative to repository or container root)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  placeholder="e.g. data/calls/call_01 or /app/data/calls/call_18"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm font-mono text-cyan-400 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50"
                  required
                />
                <button
                  type="submit"
                  disabled={loading || !folderPath.trim()}
                  className="px-6 py-2.5 rounded-xl font-medium text-xs bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 disabled:opacity-50 shrink-0"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Ingesting...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" /> Process &amp; Evaluate
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Quick Chips */}
            <div>
              <span className="text-[11px] font-mono text-slate-500 block mb-2">Quick Selection Presets:</span>
              <div className="flex flex-wrap gap-2">
                {quickPaths.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setFolderPath(p)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono border transition-all ${
                      folderPath === p
                        ? 'bg-cyan-950/60 border-cyan-500/50 text-cyan-400 font-semibold'
                        : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </form>
        )}

        {/* Tab 2: ZIP Upload */}
        {activeTab === 'upload' && (
          <div className="space-y-4">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept=".zip"
              className="hidden"
            />

            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleFileDrop}
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              className={`p-8 rounded-2xl border-2 border-dashed text-center transition-all cursor-pointer ${
                dragOver
                  ? 'border-cyan-500 bg-cyan-950/20'
                  : 'border-slate-800 hover:border-slate-700 bg-slate-950/40'
              }`}
            >
              <div className="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center mx-auto mb-3 text-cyan-400">
                <UploadCloud className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-semibold text-slate-200 mb-1">
                {selectedFile ? selectedFile.name : 'Drop call archive (.zip) here or click to browse'}
              </h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Archive must contain call.json, recording.wav, and related events.
              </p>

              {selectedFile && (
                <div className="mt-3 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/60 border border-cyan-500/30 text-xs font-mono text-cyan-300">
                  <FileCheck className="w-3.5 h-3.5" />
                  <span>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              {selectedFile && (
                <button
                  type="button"
                  onClick={() => setSelectedFile(null)}
                  className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-white"
                >
                  Clear Selection
                </button>
              )}
              <button
                type="button"
                onClick={handleUploadZip}
                disabled={loading || !selectedFile}
                className="px-6 py-2.5 rounded-xl font-medium text-xs bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Ingesting Archive...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" /> Upload &amp; Ingest
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Tab 3: Dataset Seeder */}
        {activeTab === 'seed' && (
          <div className="space-y-4">
            <p className="text-xs text-slate-400 leading-relaxed">
              Batch seed conversations from the 50 dataset folders directly into the PostgreSQL storage and run the full observability pipeline on them.
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => handleBatchSeed(10)}
                disabled={loading}
                className="px-4 py-2 rounded-xl text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-50"
              >
                Seed 10 Calls
              </button>
              <button
                onClick={() => handleBatchSeed(25)}
                disabled={loading}
                className="px-4 py-2 rounded-xl text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-50"
              >
                Seed 25 Calls
              </button>
              <button
                onClick={() => handleBatchSeed(50)}
                disabled={loading}
                className="px-4 py-2 rounded-xl text-xs font-medium bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 disabled:opacity-50"
              >
                Seed All 50 Calls
              </button>
            </div>
          </div>
        )}

        {/* Loading Progress State */}
        {loading && (
          <div className="mt-6 p-4 rounded-xl border border-cyan-500/30 bg-cyan-950/20 flex items-center gap-3 animate-pulse">
            <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
            <div>
              <p className="text-xs font-semibold text-cyan-300">Observability Pipeline In Progress</p>
              <p className="text-xs font-mono text-cyan-400/80 mt-0.5">{currentStep}</p>
            </div>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="mt-6 p-4 rounded-xl border border-rose-800 bg-rose-950/40 text-rose-300 flex items-center gap-3 text-xs">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
            <div>
              <p className="font-semibold">Ingestion Failed</p>
              <p className="text-rose-400/90 mt-0.5">{error}</p>
            </div>
          </div>
        )}
      </div>

      {/* Result Scorecard */}
      {result && (
        <div className="p-6 rounded-2xl border border-emerald-500/30 bg-emerald-950/10 backdrop-blur-md space-y-4 animate-in fade-in duration-300">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-emerald-500/20">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <div>
                <h3 className="text-sm font-bold text-white">Ingestion &amp; Evaluation Complete</h3>
                <p className="text-xs font-mono text-emerald-400">
                  Interaction: {result.interaction_id}
                </p>
              </div>
            </div>

            <button
              onClick={() => onNavigateToDrillDown && onNavigateToDrillDown(result.interaction_id)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-slate-950 transition-colors shadow-lg shadow-emerald-500/20 shrink-0"
            >
              <span>Inspect in Call Drill-Down</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] font-mono text-slate-500 block">Total Turns</span>
              <span className="text-base font-bold text-white font-mono mt-0.5 block">
                {result.events_count ?? result.reconstructed_timeline?.events?.length ?? 0}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] font-mono text-slate-500 block">Evaluators Executed</span>
              <span className="text-base font-bold text-cyan-400 font-mono mt-0.5 block">
                {result.evaluation_count ?? result.evaluations?.length ?? 0}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] font-mono text-slate-500 block">Call Duration</span>
              <span className="text-base font-bold text-slate-200 font-mono mt-0.5 block">
                {result.reconstructed_timeline?.total_duration_s
                  ? `${result.reconstructed_timeline.total_duration_s.toFixed(1)}s`
                  : 'N/A'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
              <span className="text-[10px] font-mono text-slate-500 block">Overlap Turns</span>
              <span className="text-base font-bold text-amber-400 font-mono mt-0.5 block">
                {result.reconstructed_timeline?.overlap_count ?? 0}
              </span>
            </div>
          </div>

          {/* Findings preview */}
          {result.evaluations && result.evaluations.length > 0 && (
            <div className="space-y-2 pt-2">
              <span className="text-xs font-mono text-slate-400 uppercase tracking-wider block">
                Evaluation Findings:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {result.evaluations.map((ev, i) => (
                  <div
                    key={i}
                    className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center justify-between text-xs"
                  >
                    <span className="font-mono text-slate-300">{ev.evaluator_id}</span>
                    <span
                      className={`font-semibold px-2 py-0.5 rounded text-[10px] font-mono ${
                        ev.review_status === 'PASSED'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/40'
                          : 'bg-rose-950 text-rose-400 border border-rose-800/40'
                      }`}
                    >
                      {ev.review_status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

