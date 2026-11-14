import React, { useState } from 'react';
import {
  Bot,
  User,
  Scissors,
  Volume2,
  VolumeX,
  Play,
  ChevronDown,
  ChevronUp,
  Clock,
  CheckCircle2,
  Copy,
  Check,
  Info
} from 'lucide-react';

export default function TimelineTurnCard({
  event,
  isActive,
  onSeek,
  forceExpand = null,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  // If forceExpand is explicitly true/false from parent, respect it
  const expanded = forceExpand !== null ? forceExpand : isOpen;

  const isAgent = event.speaker === 'agent';
  const start = event.start_s ?? 0;
  const end = event.end_s ?? 0;
  const duration = event.duration_s ?? (end - start);
  const deliveryStatus = event.delivery_status || event.metadata?.playback_spoken || 'heard';

  const meta = event.metadata || {};
  const normalizedText = meta.normalized_text ?? null;
  const playbackSpoken = meta.playback_spoken ?? deliveryStatus ?? null;
  const playbackHeardText = meta.playback_heard_text ?? null;
  const bargedIn = meta.barged_in ?? null;
  const deliveryEvidence = meta.delivery_evidence ?? (
    deliveryStatus === 'heard'
      ? 'Line fully heard by customer according to playback metadata'
      : deliveryStatus === 'cut'
      ? 'Line was cut during playback due to barge-in or interruption'
      : 'Playback skipped or not delivered'
  );

  const formatTime = (secs) => {
    if (secs === null || secs === undefined || isNaN(secs)) return '00:00.0';
    const m = Math.floor(secs / 60);
    const s = (secs % 60).toFixed(1);
    return `${m.toString().padStart(2, '0')}:${s.padStart(4, '0')}`;
  };

  const handleCopyText = (e) => {
    e.stopPropagation();
    const textToCopy = normalizedText || event.text || '';
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const getDeliveryPill = () => {
    const st = String(deliveryStatus).toLowerCase();
    if (st === 'heard') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/70 dark:border-emerald-500/30 dark:text-emerald-400 font-medium">
          <CheckCircle2 className="w-3 h-3" /> heard
        </span>
      );
    }
    if (st === 'cut') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/80 dark:border-rose-500/50 dark:text-rose-300 font-semibold shadow-sm">
          <Scissors className="w-3 h-3" /> cut (barge-in)
        </span>
      );
    }
    if (st === 'not_played') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">
          <VolumeX className="w-3 h-3" /> not played
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400">
        {deliveryStatus}
      </span>
    );
  };

  return (
    <div
      className={`rounded-2xl border transition-all duration-200 overflow-hidden shadow-sm dark:shadow-none ${
        isActive
          ? 'bg-white dark:bg-slate-900 border-cyan-500 ring-2 ring-cyan-500/40 shadow-md'
          : isAgent
          ? 'bg-white dark:bg-[#0d1424]/90 border-slate-200 dark:border-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700'
          : 'bg-white dark:bg-[#0c181f]/80 border-slate-200 dark:border-slate-800/70 hover:border-slate-300 dark:hover:border-slate-700'
      }`}
    >
      {/* Turn Header */}
      <div className="p-3.5 pb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Speaker Avatar Badge */}
          <div
            className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 shadow-sm ${
              isAgent
                ? 'bg-cyan-100 text-cyan-700 border border-cyan-200 dark:bg-cyan-500/15 dark:text-cyan-400 dark:border-cyan-500/30'
                : 'bg-emerald-100 text-emerald-700 border border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/30'
            }`}
          >
            {isAgent ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
          </div>

          <span
            className={`text-xs font-bold uppercase tracking-wider ${
              isAgent ? 'text-cyan-700 dark:text-cyan-400' : 'text-emerald-700 dark:text-emerald-400'
            }`}
          >
            {isAgent ? 'Agent (Voice Bot)' : 'Customer'}
          </span>

          <span className="text-slate-300 dark:text-slate-600">&bull;</span>

          {/* Timestamps */}
          <div className="flex items-center gap-1 text-[11px] font-mono text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-950/60 px-2 py-0.5 rounded-md border border-slate-200 dark:border-slate-800/60">
            <Clock className="w-3 h-3 text-slate-400 dark:text-slate-500" />
            <span>{formatTime(start)} &ndash; {formatTime(end)}</span>
            <span className="text-slate-400 dark:text-slate-500">({duration.toFixed(1)}s)</span>
          </div>
        </div>

        {/* Right side: Delivery status pill & Jump to audio button */}
        <div className="flex items-center gap-2">
          {getDeliveryPill()}

          <button
            onClick={() => onSeek && onSeek(start)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800/80 hover:bg-cyan-500 hover:text-slate-950 text-slate-700 dark:text-slate-300 text-[11px] font-mono transition-all group shadow-sm border border-slate-200 dark:border-slate-700/60"
            title="Jump audio to this turn"
          >
            <Play className="w-3 h-3 fill-current text-cyan-600 dark:text-cyan-400 group-hover:text-slate-950" />
            <span className="hidden sm:inline">Play</span>
          </button>
        </div>
      </div>

      {/* Spoken Transcript Content */}
      <div className="px-4 py-2 sm:pl-12">
        <p className="text-sm text-slate-900 dark:text-slate-100 font-sans leading-relaxed tracking-normal select-text">
          {event.text || (
            <span className="italic text-slate-400 dark:text-slate-500">[Silence / No transcription registered]</span>
          )}
        </p>
      </div>

      {/* Bottom Accordion Action Bar */}
      <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-800/50 bg-slate-50 dark:bg-slate-950/40 flex items-center justify-between transition-colors">
        <button
          onClick={() => setIsOpen(!expanded)}
          className="flex items-center gap-1.5 text-[11px] font-mono text-slate-600 dark:text-slate-400 hover:text-cyan-600 dark:hover:text-cyan-300 transition-colors font-medium"
        >
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
          )}
          <span>{expanded ? 'Hide Telemetry & Delivery Details' : 'View Telemetry & Delivery Details'}</span>
        </button>

        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-500 dark:text-slate-400">
          {normalizedText && (
            <button
              onClick={handleCopyText}
              className="flex items-center gap-1 hover:text-slate-900 dark:hover:text-slate-200 transition-colors"
              title="Copy normalized text"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" /> : <Copy className="w-3 h-3" />}
              <span>{copied ? 'Copied' : 'Copy Text'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Collapsible Inspector Drawer */}
      {expanded && (
        <div className="px-4 py-3 bg-slate-50/70 dark:bg-[#070b14] border-t border-slate-200 dark:border-slate-800 space-y-2.5 animate-in slide-in-from-top-1 duration-200">
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-600 dark:text-slate-400 uppercase tracking-wider font-semibold">
            <Info className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
            <span>Turn Reconciliation &amp; Playback Inspector</span>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-800/80 bg-white dark:bg-slate-950/80 divide-y divide-slate-100 dark:divide-slate-800/60 font-mono text-xs shadow-sm dark:shadow-none">
            {/* Normalized Text */}
            <div className="p-2.5 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400 font-semibold sm:w-44 shrink-0">normalized_text:</span>
              <span className="text-slate-900 dark:text-slate-200 font-sans text-xs break-words flex-1 bg-slate-50 dark:bg-slate-900/60 px-2 py-1 rounded border border-slate-200 dark:border-slate-800/50">
                {normalizedText !== null ? normalizedText : <span className="text-slate-400 dark:text-slate-500 italic">null</span>}
              </span>
            </div>

            {/* Playback Spoken */}
            <div className="p-2.5 flex items-center justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400 font-semibold sm:w-44 shrink-0">playback_spoken:</span>
              <span className="flex-1">
                {playbackSpoken ? (
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                    playbackSpoken === 'heard'
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-500/30'
                      : playbackSpoken === 'cut'
                      ? 'bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950 dark:text-rose-300 dark:border-rose-500/40'
                      : 'bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
                  }`}>
                    {playbackSpoken}
                  </span>
                ) : (
                  <span className="text-slate-400 dark:text-slate-500 italic">null</span>
                )}
              </span>
            </div>

            {/* Playback Heard Text */}
            <div className="p-2.5 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400 font-semibold sm:w-44 shrink-0">playback_heard_text:</span>
              <span className="text-slate-800 dark:text-slate-300 font-sans text-xs break-words flex-1">
                {playbackHeardText !== null ? (
                  <span className="bg-slate-50 dark:bg-slate-900/60 px-2 py-1 rounded border border-slate-200 dark:border-slate-800/50 inline-block">
                    &ldquo;{playbackHeardText}&rdquo;
                  </span>
                ) : (
                  <span className="text-slate-400 dark:text-slate-500 italic">null</span>
                )}
              </span>
            </div>

            {/* Barged In */}
            <div className="p-2.5 flex items-center justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400 font-semibold sm:w-44 shrink-0">barged_in:</span>
              <span className="flex-1 text-slate-800 dark:text-slate-300">
                {bargedIn !== null ? (
                  <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                    bargedIn
                      ? 'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-600/30'
                      : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                  }`}>
                    {String(bargedIn)}
                  </span>
                ) : (
                  <span className="text-slate-400 dark:text-slate-500 italic">null</span>
                )}
              </span>
            </div>

            {/* Delivery Evidence */}
            <div className="p-2.5 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
              <span className="text-slate-500 dark:text-slate-400 font-semibold sm:w-44 shrink-0">delivery_evidence:</span>
              <span className="text-cyan-800 dark:text-cyan-300 text-xs font-sans leading-relaxed flex-1 bg-cyan-50 dark:bg-cyan-950/30 p-2.5 rounded-lg border border-cyan-200 dark:border-cyan-800/30">
                {deliveryEvidence || <span className="text-slate-400 dark:text-slate-500 italic">null</span>}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
