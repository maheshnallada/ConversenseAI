import React, { useRef, useState, useEffect, useMemo } from 'react';
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  RotateCcw,
  Headphones,
  AlertCircle,
  Activity
} from 'lucide-react';

export default function AudioPlayer({
  audioUrl,
  currentTime,
  onTimeUpdate,
  onSeekTo,
  events = [],
  totalDuration = null,
}) {
  const audioRef = useRef(null);
  const waveformRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [pos, setPos] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const [hoverTime, setHoverTime] = useState(null);
  const [hoverPercent, setHoverPercent] = useState(0);

  const effectiveDuration = duration > 0 ? duration : (totalDuration > 0 ? totalDuration : 0);

  useEffect(() => {
    setPos(0);
    setIsPlaying(false);
    setAudioError(false);
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.playbackRate = playbackRate;
    }
  }, [audioUrl]);

  // When parent triggers seek
  useEffect(() => {
    if (onSeekTo !== undefined && onSeekTo !== null && audioRef.current) {
      audioRef.current.currentTime = onSeekTo;
      setPos(onSeekTo);
      if (!isPlaying) {
        audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
      }
    }
  }, [onSeekTo]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch((e) => {
          console.error('Playback error:', e);
          setAudioError(true);
        });
    }
  };

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    const t = audioRef.current.currentTime;
    setPos(t);
    if (onTimeUpdate) {
      onTimeUpdate(t);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration || 0);
    }
  };

  const cycleSpeed = () => {
    const speeds = [1, 1.25, 1.5, 2];
    const nextSpeed = speeds[(speeds.indexOf(playbackRate) + 1) % speeds.length];
    setPlaybackRate(nextSpeed);
    if (audioRef.current) {
      audioRef.current.playbackRate = nextSpeed;
    }
  };

  const toggleMute = () => {
    if (audioRef.current) {
      audioRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const formatTime = (secs) => {
    if (!secs || isNaN(secs) || secs < 0) return '00:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Generate 84 waveform bars matching timeline events
  const totalBars = 84;
  const waveformBars = useMemo(() => {
    const validDuration = effectiveDuration > 0 ? effectiveDuration : 60;
    const speechEvents = (events || []).filter(
      (e) => e.start_s != null && e.end_s != null && e.event_type !== 'silence'
    );

    return Array.from({ length: totalBars }, (_, i) => {
      const barTime = (i / totalBars) * validDuration;
      const activeEvents = speechEvents.filter(
        (e) => barTime >= e.start_s && barTime <= e.end_s
      );

      const hasAgent = activeEvents.some((e) => e.speaker === 'agent');
      const hasCustomer = activeEvents.some((e) => e.speaker === 'customer');
      const hasOverlap =
        (hasAgent && hasCustomer) ||
        activeEvents.some((e) => e.event_type === 'interruption');

      let speaker = 'silence';
      if (hasOverlap) {
        speaker = 'overlap';
      } else if (hasAgent) {
        speaker = 'agent';
      } else if (hasCustomer) {
        speaker = 'customer';
      }

      // Organic wave shaping
      const pseudoNoise =
        0.35 +
        0.35 * Math.sin(i * 0.45) * Math.cos(i * 0.18 + 0.5) +
        0.2 * Math.sin(i * 1.8);
      const isSpeaking = speaker !== 'silence';
      const heightPercent = isSpeaking
        ? Math.min(95, Math.max(30, Math.round(pseudoNoise * 90 + 20)))
        : Math.min(25, Math.max(12, Math.round(pseudoNoise * 15 + 8)));

      return {
        id: i,
        time: barTime,
        speaker,
        height: heightPercent,
      };
    });
  }, [effectiveDuration, events]);

  const handleWaveformClick = (e) => {
    if (!waveformRef.current || !effectiveDuration) return;
    const rect = waveformRef.current.getBoundingClientRect();
    const clickX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const targetSeconds = (clickX / rect.width) * effectiveDuration;
    setPos(targetSeconds);
    if (audioRef.current) {
      audioRef.current.currentTime = targetSeconds;
    }
    if (onTimeUpdate) {
      onTimeUpdate(targetSeconds);
    }
  };

  const handleWaveformMouseMove = (e) => {
    if (!waveformRef.current || !effectiveDuration) return;
    const rect = waveformRef.current.getBoundingClientRect();
    const hoverX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
    const percent = (hoverX / rect.width) * 100;
    const seconds = (hoverX / rect.width) * effectiveDuration;
    setHoverPercent(percent);
    setHoverTime(seconds);
  };

  const handleWaveformMouseLeave = () => {
    setHoverTime(null);
  };

  const currentPercent = effectiveDuration > 0 ? (pos / effectiveDuration) * 100 : 0;

  return (
    <div className="p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/90 shadow-sm dark:shadow-none backdrop-blur-md transition-colors space-y-3">
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={() => setIsPlaying(false)}
        onError={() => setAudioError(true)}
        preload="metadata"
      />

      {/* 1. Interactive Audio Waveform Header */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5 text-slate-700 dark:text-slate-300 font-bold">
            <Activity className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
            <span>Audio Waveform</span>
          </div>
          <div className="flex items-center gap-2.5 text-[11px] font-sans">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-cyan-500 inline-block" />
              <span className="text-slate-600 dark:text-slate-400">Agent</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
              <span className="text-slate-600 dark:text-slate-400">Customer</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
              <span className="text-slate-600 dark:text-slate-400">Overlap</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-700 inline-block" />
              <span className="text-slate-400 dark:text-slate-500">Silence</span>
            </span>
          </div>
        </div>

        {/* Waveform Canvas / Bars Container */}
        <div
          ref={waveformRef}
          onClick={handleWaveformClick}
          onMouseMove={handleWaveformMouseMove}
          onMouseLeave={handleWaveformMouseLeave}
          className="relative h-16 w-full rounded-xl bg-slate-50 dark:bg-slate-950/80 border border-slate-200/80 dark:border-slate-800/80 cursor-pointer overflow-hidden flex items-center justify-between px-1.5 select-none group"
          title="Click to seek audio"
        >
          {/* Waveform Bars */}
          {waveformBars.map((bar, idx) => {
            const barProgress = (idx / totalBars) * 100;
            const isPlayed = barProgress <= currentPercent;

            let barColor = 'bg-slate-300 dark:bg-slate-700';
            if (bar.speaker === 'overlap') {
              barColor = isPlayed
                ? 'bg-amber-400 shadow-sm shadow-amber-400/50'
                : 'bg-amber-400/50 dark:bg-amber-400/40';
            } else if (bar.speaker === 'agent') {
              barColor = isPlayed
                ? 'bg-cyan-500 shadow-sm shadow-cyan-500/50'
                : 'bg-cyan-500/40 dark:bg-cyan-500/30';
            } else if (bar.speaker === 'customer') {
              barColor = isPlayed
                ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50'
                : 'bg-emerald-500/40 dark:bg-emerald-500/30';
            } else {
              barColor = isPlayed
                ? 'bg-slate-400 dark:bg-slate-500'
                : 'bg-slate-200 dark:bg-slate-800';
            }

            return (
              <div
                key={bar.id}
                className="flex-1 flex items-center justify-center h-full px-[0.5px]"
              >
                <div
                  style={{ height: `${bar.height}%` }}
                  className={`w-full rounded-full transition-all duration-75 ${barColor} group-hover:brightness-110`}
                />
              </div>
            );
          })}

          {/* Current Playhead Line */}
          <div
            style={{ left: `${currentPercent}%` }}
            className="absolute top-0 bottom-0 w-0.5 bg-cyan-600 dark:bg-cyan-400 shadow-lg shadow-cyan-500/80 pointer-events-none z-10 transition-all duration-75"
          >
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-500 -ml-1 -mt-0.5 shadow-md border-2 border-white dark:border-slate-950" />
          </div>

          {/* Hover Time Scrubber Tooltip */}
          {hoverTime !== null && (
            <div
              style={{ left: `${hoverPercent}%` }}
              className="absolute top-1 -translate-x-1/2 px-1.5 py-0.5 rounded bg-slate-900 dark:bg-white text-white dark:text-slate-950 font-mono text-[10px] font-bold shadow-lg pointer-events-none z-20 whitespace-nowrap"
            >
              {formatTime(hoverTime)}
            </div>
          )}
        </div>

        {/* Dual-Channel Speaker Track Ribbon (Ch 1 Agent on Top, Ch 2 Customer on Bottom) */}
        <div className="space-y-1">
          <div className="relative h-4 w-full rounded-md bg-slate-100 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800/80 overflow-hidden select-none">
            {/* Subtle dividing line between Agent (top) and Customer (bottom) */}
            <div className="absolute top-1/2 left-0 right-0 h-[1px] bg-slate-200 dark:bg-slate-800 pointer-events-none" />

            {/* Playhead indicator on ribbon */}
            <div
              style={{ left: `${currentPercent}%` }}
              className="absolute top-0 bottom-0 w-0.5 bg-cyan-600 dark:bg-cyan-400 z-30 pointer-events-none"
            />

            {events && events.length > 0 && effectiveDuration > 0 ? (
              events.map((ev, i) => {
                if (ev.start_s == null || ev.end_s == null) return null;
                const left = Math.max(0, Math.min(100, (ev.start_s / effectiveDuration) * 100));
                const width = Math.max(0.6, Math.min(100 - left, ((ev.end_s - ev.start_s) / effectiveDuration) * 100));

                if (ev.event_type === 'interruption') {
                  return (
                    <div
                      key={ev.event_id || `overlap_${i}`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                      className="absolute top-0 bottom-0 bg-amber-400/90 dark:bg-amber-400 z-20 rounded-xs ring-1 ring-amber-500/40"
                      title={`Overlap: ${ev.start_s.toFixed(1)}s - ${ev.end_s.toFixed(1)}s (${ev.duration_s?.toFixed(1) || ''}s)`}
                    />
                  );
                }

                if (ev.speaker === 'agent') {
                  return (
                    <div
                      key={ev.event_id || `agent_${i}`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                      className="absolute top-0.5 h-[6px] bg-cyan-500 dark:bg-cyan-400 rounded-xs opacity-90 hover:opacity-100 transition-opacity z-10"
                      title={`Agent Turn: ${ev.start_s.toFixed(1)}s - ${ev.end_s.toFixed(1)}s`}
                    />
                  );
                }

                if (ev.speaker === 'customer') {
                  return (
                    <div
                      key={ev.event_id || `customer_${i}`}
                      style={{ left: `${left}%`, width: `${width}%` }}
                      className="absolute bottom-0.5 h-[6px] bg-emerald-500 dark:bg-emerald-400 rounded-xs opacity-90 hover:opacity-100 transition-opacity z-10"
                      title={`Customer Turn: ${ev.start_s.toFixed(1)}s - ${ev.end_s.toFixed(1)}s: "${ev.text || ''}"`}
                    />
                  );
                }

                return null;
              })
            ) : (
              <div
                style={{ width: `${currentPercent}%` }}
                className="h-full bg-cyan-500 rounded-full"
              />
            )}
          </div>
          <div className="flex items-center justify-between text-[10px] font-mono text-slate-600 dark:text-slate-300 px-0.5">
            <span>Ch 1: Agent</span>
            <span>Ch 2: Customer</span>
          </div>
        </div>
      </div>

      {/* 2. Controls & Scrubber Row */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-slate-100 dark:border-slate-800/80">
        {/* Controls Group */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          <button
            onClick={togglePlay}
            disabled={audioError}
            className={`w-9 h-9 rounded-xl flex items-center justify-center font-semibold transition-all shadow-sm ${
              isPlaying
                ? 'bg-cyan-500 text-slate-950 shadow-cyan-500/25 ring-2 ring-cyan-400'
                : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-700'
            }`}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4 fill-current" />
            ) : (
              <Play className="w-4 h-4 fill-current ml-0.5" />
            )}
          </button>

          <button
            onClick={() => {
              if (audioRef.current) {
                audioRef.current.currentTime = Math.max(
                  0,
                  audioRef.current.currentTime - 5
                );
              }
            }}
            className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700/60 transition-colors"
            title="Rewind 5s"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={cycleSpeed}
            className="px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700 text-[11px] font-sans font-bold text-cyan-700 dark:text-cyan-400 border border-slate-200 dark:border-slate-700/60 transition-colors"
            title="Change Playback Speed"
          >
            {playbackRate}x
          </button>

          <button
            onClick={toggleMute}
            className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700/60 transition-colors"
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted ? (
              <VolumeX className="w-3.5 h-3.5 text-rose-500" />
            ) : (
              <Volume2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>

        {/* Time display & Channels Info */}
        <div className="flex items-center gap-2 sm:gap-3 text-xs">
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-slate-500 dark:text-slate-400 font-sans text-[11px]">
            <Headphones className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
            <span>Stereo: Ch 1 Agent &bull; Ch 2 Customer</span>
          </div>

          <div className="font-mono text-xs text-slate-700 dark:text-slate-200 bg-slate-50 dark:bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-800 font-medium">
            <span className="text-cyan-700 dark:text-cyan-400 font-bold">
              {formatTime(pos)}
            </span>
            <span className="text-slate-400 mx-1">/</span>
            <span>{formatTime(effectiveDuration)}</span>
          </div>
        </div>
      </div>

      {audioError && (
        <div className="text-xs text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/40 rounded-xl px-3 py-1.5 flex items-center justify-between font-sans">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>Audio recording unavailable for this interaction.</span>
          </div>
          <span className="font-mono text-[10px] text-slate-500">/audio</span>
        </div>
      )}
    </div>
  );
}
