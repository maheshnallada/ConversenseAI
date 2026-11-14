import React from 'react';
import { Scissors, Clock, Play } from 'lucide-react';

export default function TimelineMarker({ event, onSeek }) {
  const isInterruption = event.event_type === 'interruption';
  const duration = event.duration_s ? event.duration_s.toFixed(1) : '0.0';
  const interrupter = event.metadata?.interrupter || event.speaker || 'party';

  if (isInterruption) {
    return (
      <div className="my-2.5 flex items-center justify-center">
        <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-500/40 text-rose-700 dark:text-rose-300 text-[11px] font-mono shadow-sm">
          <Scissors className="w-3.5 h-3.5 text-rose-500 dark:text-rose-400" />
          <span>Speech Overlap: <strong>{duration}s</strong> ({interrupter} barged in)</span>
          {event.start_s !== undefined && onSeek && (
            <button
              onClick={() => onSeek(event.start_s)}
              className="ml-1 p-0.5 rounded hover:bg-rose-100 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 transition-colors"
              title="Jump audio to overlap"
            >
              <Play className="w-2.5 h-2.5 fill-current" />
            </button>
          )}
        </div>
      </div>
    );
  }

  // Silence event
  return (
    <div className="my-2 flex items-center justify-center">
      <div className="flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-slate-100 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-slate-500 text-[10px] font-mono">
        <Clock className="w-3 h-3 text-slate-400" />
        <span>Silence pause ({duration}s)</span>
      </div>
    </div>
  );
}
