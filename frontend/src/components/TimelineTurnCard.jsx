import React from 'react';
import { Bot, User, Scissors, Volume2, VolumeX, PlayCircle } from 'lucide-react';

export default function TimelineTurnCard({ event, isActive, onSeek }) {
  const isAgent = event.speaker === 'agent';
  const start = event.start_s ?? 0;
  const end = event.end_s ?? 0;
  const duration = event.duration_s ?? (end - start);
  const status = event.delivery_status || 'heard';

  const formatTime = (secs) => {
    if (secs === null || secs === undefined || isNaN(secs)) return '00:00.0';
    const m = Math.floor(secs / 60);
    const s = (secs % 60).toFixed(1);
    return `${m.toString().padStart(2, '0')}:${s.padStart(4, '0')}`;
  };

  const getStatusBadge = () => {
    switch (status.toLowerCase()) {
      case 'heard':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-500/30 text-emerald-400">
            <Volume2 className="w-3 h-3" /> heard
          </span>
        );
      case 'cut':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-rose-950/70 border border-rose-500/40 text-rose-400 font-semibold shadow-sm shadow-rose-950">
            <Scissors className="w-3 h-3" /> cut (interrupted)
          </span>
        );
      case 'not_played':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400">
            <VolumeX className="w-3 h-3" /> not played
          </span>
        );
      default:
        return (
          <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
            {status}
          </span>
        );
    }
  };

  return (
    <div
      onClick={() => onSeek && onSeek(start)}
      className={`group relative p-3.5 rounded-xl border transition-all duration-200 cursor-pointer ${
        isActive
          ? 'bg-cyan-950/40 border-cyan-500/60 shadow-lg shadow-cyan-950/30 ring-1 ring-cyan-500/40'
          : isAgent
          ? 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900'
          : 'bg-slate-900/40 border-slate-800/60 hover:border-slate-700 hover:bg-slate-900/80'
      }`}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div
            className={`w-6 h-6 rounded-md flex items-center justify-center ${
              isAgent ? 'bg-cyan-500/20 text-cyan-400' : 'bg-emerald-500/20 text-emerald-400'
            }`}
          >
            {isAgent ? <Bot className="w-3.5 h-3.5" /> : <User className="w-3.5 h-3.5" />}
          </div>
          <span className={`text-xs font-semibold uppercase tracking-wider ${isAgent ? 'text-cyan-400' : 'text-emerald-400'}`}>
            {isAgent ? 'Agent' : 'Customer'}
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            {formatTime(start)} &ndash; {formatTime(end)}
          </span>
          <span className="text-[10px] font-mono text-slate-500">
            ({duration.toFixed(1)}s)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {getStatusBadge()}
          <PlayCircle className="w-4 h-4 text-slate-600 group-hover:text-cyan-400 transition-colors opacity-0 group-hover:opacity-100" />
        </div>
      </div>

      {/* Transcript Text */}
      <p className="text-sm text-slate-200 leading-relaxed font-sans pl-8">
        {event.text || <span className="italic text-slate-500">[Silence / No transcription]</span>}
      </p>

      {/* Metadata tags if present */}
      {event.metadata && Object.keys(event.metadata).length > 0 && (
        <div className="mt-2 pl-8 flex flex-wrap gap-1.5 text-[10px] font-mono text-slate-400">
          {Object.entries(event.metadata).map(([k, v]) => (
            <span key={k} className="px-1.5 py-0.5 rounded bg-slate-950/60 border border-slate-800">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

