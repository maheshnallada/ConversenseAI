import React from 'react';
import { Scissors, Clock, Play, CalendarCheck, PhoneForwarded } from 'lucide-react';

export default function TimelineMarker({ event, onSeek }) {
  const isInterruption = event.event_type === 'interruption';
  const isBooking =
    event.event_type === 'booking' || event.event_type === 'appointment.booked';
  const isCallback =
    event.event_type === 'callback' ||
    event.event_type === 'callback.scheduled';

  const duration = event.duration_s == null
    ? 'Unavailable'
    : event.duration_s.toFixed(1);
  const interrupter = event.metadata?.interrupter || event.speaker || 'party';

  if (isBooking) {
    const meta = event.metadata || {};
    const apptTime = meta.appointment_at || meta.expert_call_at || event.text;
    const commitments = meta.commitments || [];
    const commitmentText =
      commitments.length > 0
        ? commitments.map((c) => c.what || c.date).join(', ')
        : null;

    return (
      <div className="my-3 flex items-center justify-center">
        <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-300 dark:border-emerald-600/50 text-emerald-800 dark:text-emerald-200 text-xs shadow-sm">
          <CalendarCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
            <span className="font-bold tracking-tight uppercase text-[11px] text-emerald-900 dark:text-emerald-100">
              Appointment Booked
            </span>
            {apptTime && (
              <span className="font-mono text-emerald-700 dark:text-emerald-300">
                {apptTime}
              </span>
            )}
            {commitmentText && (
              <span className="text-emerald-600 dark:text-emerald-400 italic text-[11px]">
                ({commitmentText})
              </span>
            )}
          </div>
          {event.start_s !== undefined && onSeek && (
            <button
              onClick={() => onSeek(event.start_s)}
              className="ml-1 p-1 rounded-lg hover:bg-emerald-100 dark:hover:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 transition-colors"
              title="Jump audio to booking"
            >
              <Play className="w-2.5 h-2.5 fill-current" />
            </button>
          )}
        </div>
      </div>
    );
  }

  if (isCallback) {
    const meta = event.metadata || {};
    const cbTime = meta.callback_at || meta.call_later_at || event.text;
    const commitments = meta.commitments || [];
    const commitmentText =
      commitments.length > 0
        ? commitments.map((c) => c.what || c.date).join(', ')
        : null;

    return (
      <div className="my-3 flex items-center justify-center">
        <div className="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl bg-sky-50 dark:bg-sky-950/60 border border-sky-300 dark:border-sky-600/50 text-sky-800 dark:text-sky-200 text-xs shadow-sm">
          <PhoneForwarded className="w-4 h-4 text-sky-600 dark:text-sky-400 shrink-0" />
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
            <span className="font-bold tracking-tight uppercase text-[11px] text-sky-900 dark:text-sky-100">
              Callback Scheduled
            </span>
            {cbTime && (
              <span className="font-mono text-sky-700 dark:text-sky-300">
                {cbTime}
              </span>
            )}
            {commitmentText && (
              <span className="text-sky-600 dark:text-sky-400 italic text-[11px]">
                ({commitmentText})
              </span>
            )}
          </div>
          {event.start_s !== undefined && onSeek && (
            <button
              onClick={() => onSeek(event.start_s)}
              className="ml-1 p-1 rounded-lg hover:bg-sky-100 dark:hover:bg-sky-900/60 text-sky-700 dark:text-sky-300 transition-colors"
              title="Jump audio to callback marker"
            >
              <Play className="w-2.5 h-2.5 fill-current" />
            </button>
          )}
        </div>
      </div>
    );
  }

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
