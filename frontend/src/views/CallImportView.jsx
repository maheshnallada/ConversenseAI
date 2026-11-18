import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  CloudUpload,
  FolderOpen,
  RefreshCw,
  Upload,
} from 'lucide-react';
import { api } from '../api/client';

const isSuccessful = (status) => status === 'created' || status === 'replayed';

function getRelativePath(file) {
  return (file.webkitRelativePath || file.name).replace(/\\/g, '/');
}

function groupUploadFiles(files) {
  const entries = files.map((file) => {
    const parts = getRelativePath(file).split('/');
    return { file, parts, parent: parts.slice(0, -1) };
  });
  const commonParent = [];
  for (const [index, part] of (entries[0]?.parent || []).entries()) {
    if (entries.every((entry) => entry.parent[index]?.toLowerCase() === part.toLowerCase())) {
      commonParent.push(part);
    } else {
      break;
    }
  }

  const hasRootLevelFile = entries.some(
    (entry) => entry.parent.length === commonParent.length,
  );
  const groups = new Map();
  for (const entry of entries) {
    const root = hasRootLevelFile
      ? commonParent
      : entry.parent.length > commonParent.length
        ? [...commonParent, entry.parent[commonParent.length]]
        : commonParent;
    const key = root.join('/');
    if (!groups.has(key)) {
      groups.set(key, {
        folderName: root.at(-1) || 'Uploaded call',
        files: [],
      });
    }
    groups.get(key).files.push(entry.file);
  }
  return [...groups.values()];
}

function StatusBadge({ status }) {
  const classes = {
    created: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-700',
    replayed: 'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-700',
    invalid: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-700',
    conflict: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-700',
    failed: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-700',
  };
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold capitalize ${classes[status] || classes.failed}`}>
      {status}
    </span>
  );
}

function ProcessingStatusBadge({ label, status }) {
  const classes = status === 'ready'
    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
    : status === 'failed'
      ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300'
      : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] ${classes}`}>
      <span className="font-semibold">{label}:</span>
      <span className="capitalize">{status || 'unknown'}</span>
    </span>
  );
}

export default function CallImportView({ onInspectCall }) {
  const [mode, setMode] = useState('single');
  const [source, setSource] = useState('computer');
  const [stagedRefreshKey, setStagedRefreshKey] = useState(0);
  const [stagedCalls, setStagedCalls] = useState([]);
  const [selectedFolderIds, setSelectedFolderIds] = useState([]);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [results, setResults] = useState(null);
  const [lastStagedFolderIds, setLastStagedFolderIds] = useState([]);
  const [loadingStaged, setLoadingStaged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (source !== 'staged') return undefined;
    let active = true;
    setLoadingStaged(true);
    setError(null);
    api.getStagedCallFolders()
      .then((response) => {
        if (active) setStagedCalls(response.calls || []);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message || 'Could not load staged calls.');
      })
      .finally(() => {
        if (active) setLoadingStaged(false);
      });
    return () => {
      active = false;
    };
  }, [source, stagedRefreshKey]);

  function chooseSource(nextSource) {
    setSource(nextSource);
    setSelectedFolderIds([]);
    setError(null);
  }

  function handleFileChange(event) {
    setUploadFiles(Array.from(event.target.files || []));
    setResults(null);
    setError(null);
  }

  function toggleStagedFolder(folderId) {
    if (mode === 'single') {
      setSelectedFolderIds([folderId]);
      return;
    }
    setSelectedFolderIds((current) => (
      current.includes(folderId)
        ? current.filter((id) => id !== folderId)
        : [...current, folderId]
    ));
  }

  async function importStaged(folderIds, mergeFailed = false) {
    if (!folderIds.length) return;
    setSubmitting(true);
    setError(null);
    if (!mergeFailed) {
      setLastStagedFolderIds(folderIds);
      setResults({ total_calls: 0, created: 0, replayed: 0, invalid: 0, failed: 0, calls: [] });
    }
    try {
      for (let i = 0; i < folderIds.length; i++) {
        const folderId = folderIds[i];
        const folderSummary = stagedCalls.find((c) => c.folder_id === folderId);
        setProgress({
          current: i + 1,
          total: folderIds.length,
          name: folderSummary?.display_name || folderId,
        });
        try {
          const response = await api.importStagedCallFolders([folderId]);
          setResults((prev) =>
            mergeFailed ? mergeFailedResults(prev, response) : appendCallResult(prev, response),
          );
        } catch (requestError) {
          const failedCall = {
            folder_name: folderSummary?.display_name || folderId,
            interaction_id: null,
            status: 'failed',
            reconstruction: { status: 'failed', error: requestError.message || 'Import failed.' },
            observability: { status: 'failed' },
            evaluation: { status: 'failed' },
            error: requestError.message || 'Import failed.',
          };
          const failureBatch = {
            total_calls: 1,
            created: 0,
            replayed: 0,
            invalid: 0,
            failed: 1,
            calls: [failedCall],
          };
          setResults((prev) =>
            mergeFailed ? mergeFailedResults(prev, failureBatch) : appendCallResult(prev, failureBatch),
          );
        }
      }
    } finally {
      setProgress(null);
      setSubmitting(false);
    }
  }

  async function importUploadGroups(groups, mergeFailed = false) {
    if (!groups.length) return;
    setSubmitting(true);
    setError(null);
    if (!mergeFailed) {
      setResults({ total_calls: 0, created: 0, replayed: 0, invalid: 0, failed: 0, calls: [] });
    }
    try {
      for (let i = 0; i < groups.length; i++) {
        const group = groups[i];
        setProgress({
          current: i + 1,
          total: groups.length,
          name: group.folderName,
        });
        try {
          const response = await api.importCallFolderFiles(group.files);
          setResults((prev) =>
            mergeFailed ? mergeFailedResults(prev, response) : appendCallResult(prev, response),
          );
        } catch (requestError) {
          const failedCall = {
            folder_name: group.folderName,
            interaction_id: null,
            status: 'failed',
            reconstruction: { status: 'failed', error: requestError.message || 'Import failed.' },
            observability: { status: 'failed' },
            evaluation: { status: 'failed' },
            error: requestError.message || 'Import failed.',
          };
          const failureBatch = {
            total_calls: 1,
            created: 0,
            replayed: 0,
            invalid: 0,
            failed: 1,
            calls: [failedCall],
          };
          setResults((prev) =>
            mergeFailed ? mergeFailedResults(prev, failureBatch) : appendCallResult(prev, failureBatch),
          );
        }
      }
    } finally {
      setProgress(null);
      setSubmitting(false);
    }
  }

  function handleImport(event) {
    event.preventDefault();
    if (source === 'staged') {
      if (selectedFolderIds.length === 0) {
        setError('Select at least one staged call to import.');
        return;
      }
      importStaged(selectedFolderIds);
      return;
    }
    if (uploadFiles.length === 0) {
      setError('Choose a call folder before importing.');
      return;
    }
    const manifestCount = uploadFiles.filter((file) =>
      getRelativePath(file).split('/').at(-1)?.toLowerCase() === 'call.json',
    ).length;
    if (mode === 'single' && manifestCount > 1) {
      setError('More than one call.json was selected. Choose Folder batch for multiple calls.');
      return;
    }
    const groups = groupUploadFiles(uploadFiles);
    importUploadGroups(groups);
  }

  function handleRetryFailed() {
    if (!results) return;
    const failedIndexes = results.calls
      .map((call, index) => (isSuccessful(call.status) ? -1 : index))
      .filter((index) => index >= 0);
    if (source === 'staged') {
      const failedFolderIds = failedIndexes
        .map((index) => lastStagedFolderIds[index])
        .filter(Boolean);
      if (failedFolderIds.length) importStaged(failedFolderIds, true);
      return;
    }
    const groups = groupUploadFiles(uploadFiles);
    const retryGroups = failedIndexes.map((index) => groups[index]).filter(Boolean);
    if (retryGroups.length) importUploadGroups(retryGroups, true);
  }

  const failedCount = results?.calls.filter((call) => !isSuccessful(call.status)).length || 0;
  const selectedIds = new Set(selectedFolderIds);

  return (
    <div className="space-y-5">
      <header className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-500/10 dark:text-cyan-400">
            <CloudUpload className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Import calls</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
              Successfully imported calls are processed for transcript, observability, and evaluation results. Any stage errors are shown with each result.
            </p>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              Each call folder must contain <code>call.json</code> and <code>recording.wav</code>.
              Upload limits are 512 MiB per file and 5 GiB per request.
            </p>
          </div>
        </div>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Import mode
            </h3>
            <div className="flex flex-wrap gap-2">
              {[
                ['single', 'Single call'],
                ['batch', 'Folder batch'],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={mode === value}
                  onClick={() => {
                    setMode(value);
                    setSelectedFolderIds([]);
                    setError(null);
                  }}
                  className={`rounded-xl border px-3.5 py-2 text-xs font-semibold ${
                    mode === value
                      ? 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-500/40 dark:bg-cyan-500/10 dark:text-cyan-300'
                      : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-950/50 dark:text-slate-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Call source
            </h3>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                aria-pressed={source === 'computer'}
                onClick={() => chooseSource('computer')}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold ${
                  source === 'computer'
                    ? 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-500/40 dark:bg-cyan-500/10 dark:text-cyan-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-950/50 dark:text-slate-300'
                }`}
              >
                <FolderOpen className="h-4 w-4" />
                Upload from computer
              </button>
              <button
                type="button"
                aria-pressed={source === 'staged'}
                onClick={() => chooseSource('staged')}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold ${
                  source === 'staged'
                    ? 'border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-500/40 dark:bg-cyan-500/10 dark:text-cyan-300'
                    : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-950/50 dark:text-slate-300'
                }`}
              >
                <Upload className="h-4 w-4" />
                Staged backend calls
              </button>
            </div>
          </div>

          {source === 'computer' ? (
            <form onSubmit={handleImport} className="space-y-3">
              <label className="block rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 dark:border-slate-700 dark:bg-slate-950/40">
                <span className="block text-xs font-semibold text-slate-800 dark:text-slate-200">
                  Choose a call folder or a parent folder containing calls
                </span>
                <span className="mt-1 block text-[11px] text-slate-500 dark:text-slate-400">
                  Folder structure is used only to group files for this upload.
                </span>
                <input
                  type="file"
                  multiple
                  webkitdirectory=""
                  directory=""
                  onChange={handleFileChange}
                  className="mt-3 block w-full text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-cyan-100 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-cyan-800 dark:text-slate-300 dark:file:bg-cyan-950/60 dark:file:text-cyan-300"
                />
              </label>
              {uploadFiles.length > 0 && (
                <p className="text-xs text-slate-600 dark:text-slate-300">
                  {uploadFiles.length} file{uploadFiles.length === 1 ? '' : 's'} selected
                </p>
              )}
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-700 px-4 py-2.5 text-xs font-semibold text-white hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
              >
                {submitting ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                {submitting
                  ? progress
                    ? `Processing ${progress.current} of ${progress.total}...`
                    : 'Importing calls...'
                  : 'Import selected calls'}
              </button>
            </form>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-slate-600 dark:text-slate-300">
                  {mode === 'single' ? 'Select one staged call.' : 'Select the staged calls to import.'}
                </p>
                <button
                  type="button"
                  onClick={() => setStagedRefreshKey((key) => key + 1)}
                  disabled={loadingStaged}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loadingStaged ? 'animate-spin' : ''}`} />
                  Refresh list
                </button>
              </div>
              {loadingStaged ? (
                <p className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500 dark:bg-slate-950/40">
                  Loading staged calls...
                </p>
              ) : stagedCalls.length === 0 ? (
                <p className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500 dark:bg-slate-950/40">
                  No staged call folders were found for this tenant.
                </p>
              ) : (
                <div className="max-h-80 divide-y divide-slate-100 overflow-y-auto rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
                  {stagedCalls.map((call) => (
                    <label
                      key={call.folder_id}
                      className="flex cursor-pointer items-start gap-3 p-3 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <input
                        type={mode === 'single' ? 'radio' : 'checkbox'}
                        name="staged-call"
                        checked={selectedIds.has(call.folder_id)}
                        onChange={() => toggleStagedFolder(call.folder_id)}
                        className="mt-0.5 accent-cyan-600"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="truncate text-xs font-semibold text-slate-800 dark:text-slate-200">
                            {call.display_name}
                          </span>
                          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            call.is_ready
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                              : 'bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300'
                          }`}>
                            {call.is_ready ? 'Ready' : 'Needs attention'}
                          </span>
                        </span>
                        {call.validation_errors?.length > 0 && (
                          <span className="mt-1 block text-[11px] text-amber-700 dark:text-amber-300">
                            {call.validation_errors.join(' ')}
                          </span>
                        )}
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <button
                type="button"
                onClick={() => importStaged(selectedFolderIds)}
                disabled={submitting || loadingStaged || selectedFolderIds.length === 0}
                className="inline-flex items-center gap-2 rounded-xl bg-cyan-700 px-4 py-2.5 text-xs font-semibold text-white hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
              >
                {submitting ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                {submitting
                  ? progress
                    ? `Processing ${progress.current} of ${progress.total}...`
                    : 'Importing calls...'
                  : 'Import selected calls'}
              </button>
            </div>
          )}

          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
      </section>

      {results && (
        <section aria-live="polite" className="space-y-3">
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {submitting ? (
                  <RefreshCw className="h-4 w-4 animate-spin text-cyan-600 dark:text-cyan-400" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
                )}
                <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                  {results.total_calls} call{results.total_calls === 1 ? '' : 's'} processed
                  {submitting && progress ? ` (processing ${progress.current} of ${progress.total}${progress.name ? `: ${progress.name}` : ''})` : ''}:
                  {' '}{results.created} created, {results.replayed} replayed, {results.failed} failed
                </p>
              </div>
              {failedCount > 0 && (
                <button
                  type="button"
                  onClick={handleRetryFailed}
                  disabled={submitting}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 disabled:opacity-50 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${submitting ? 'animate-spin' : ''}`} />
                  Retry failed calls
                </button>
              )}
            </div>
            {submitting && progress && progress.total > 0 && (
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full bg-cyan-600 transition-all duration-300 dark:bg-cyan-400"
                  style={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
                />
              </div>
            )}
          </div>
          <div className="space-y-3">
            {results.calls.map((call, index) => (
              <article
                key={`${call.interaction_id || call.folder_name}-${index}`}
                className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-bold text-slate-900 dark:text-slate-100">
                      {call.folder_name}
                    </h3>
                    <p className="mt-1 break-all font-mono text-[11px] text-slate-500 dark:text-slate-400">
                      {call.interaction_id || 'Call ID unavailable'}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={call.status} />
                    {isSuccessful(call.status) && call.interaction_id && (
                      <button
                        type="button"
                        onClick={() => onInspectCall(call.interaction_id)}
                        className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-1.5 text-xs font-semibold text-cyan-800 hover:bg-cyan-100 dark:border-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-300 dark:hover:bg-cyan-950/70"
                      >
                        Inspect call
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                  <span>{call.files_count} files</span>
                  <span>
                    Audio: {call.audio_validation?.is_valid ? 'valid WAV' : 'invalid or missing'}
                  </span>
                  {call.audio_validation?.channels != null && (
                    <span>{call.audio_validation.channels} channel{call.audio_validation.channels === 1 ? '' : 's'}</span>
                  )}
                  {call.audio_validation?.sample_rate != null && (
                    <span>{call.audio_validation.sample_rate.toLocaleString()} Hz</span>
                  )}
                  {call.audio_validation?.duration_s != null && (
                    <span>{call.audio_validation.duration_s}s</span>
                  )}
                  {call.audio_validation?.is_silent && <span>Silent recording</span>}
                </div>
                {call.validation_errors?.length > 0 && (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-700 dark:text-amber-300">
                    {call.validation_errors.map((message, errorIndex) => (
                      <li key={`${errorIndex}-${message}`}>{message}</li>
                    ))}
                  </ul>
                )}
                {call.error && (
                  <p className="mt-3 rounded-lg bg-rose-50 p-2.5 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                    {call.error}
                  </p>
                )}
                {call.processing ? (
                  <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/40">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        Post-import processing
                      </h4>
                      <span className="text-[11px] text-slate-600 dark:text-slate-300">
                        Transcript turns: {call.processing.transcript_turns}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <ProcessingStatusBadge
                        label="Timeline"
                        status={call.processing.timeline_status}
                      />
                      <ProcessingStatusBadge
                        label="Observability"
                        status={call.processing.observability_status}
                      />
                      <ProcessingStatusBadge
                        label="Evaluation"
                        status={call.processing.evaluation_status}
                      />
                    </div>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">
                      Evaluation run: {call.processing.evaluation_run_id || 'Not available'}
                    </p>
                    {call.processing.errors?.length > 0 && (
                      <ul className="space-y-1 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300">
                        {call.processing.errors.map((error, errorIndex) => (
                          <li key={`${error.stage}-${errorIndex}`}>
                            <span className="font-semibold capitalize">{error.stage}:</span>
                            {' '}{error.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="mt-3 text-[11px] text-slate-500 dark:text-slate-400">
                    Post-import processing was not run for this result.
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function appendCallResult(previous, response) {
  const currentCalls = previous?.calls || [];
  const nextCalls = [...currentCalls, ...(response.calls || [])];
  return {
    total_calls: nextCalls.length,
    created: (previous?.created || 0) + (response.created || 0),
    replayed: (previous?.replayed || 0) + (response.replayed || 0),
    invalid: (previous?.invalid || 0) + (response.invalid || 0),
    failed: (previous?.failed || 0) + (response.failed || 0),
    calls: nextCalls,
  };
}

function mergeFailedResults(previous, retry) {
  if (!previous) return retry;
  const retryCallsByFolder = new Map(
    (retry.calls || []).map((call) => [call.folder_name, call]),
  );
  const remainingRetry = [...(retry.calls || [])];
  const calls = previous.calls.map((call) => {
    if (isSuccessful(call.status)) return call;
    if (call.folder_name && retryCallsByFolder.has(call.folder_name)) {
      const match = retryCallsByFolder.get(call.folder_name);
      retryCallsByFolder.delete(call.folder_name);
      return match;
    }
    return remainingRetry.shift() || call;
  });
  return {
    total_calls: calls.length,
    created: calls.filter((call) => call.status === 'created').length,
    replayed: calls.filter((call) => call.status === 'replayed').length,
    invalid: calls.filter((call) => call.status === 'invalid').length,
    failed: calls.filter((call) => !isSuccessful(call.status)).length,
    calls,
  };
}
