import React, { useRef, useState, useEffect } from 'react';
import { Play, Pause, Volume2, VolumeX, RotateCcw, FastForward, Headphones } from 'lucide-react';

export default function AudioPlayer({ audioUrl, currentTime, onTimeUpdate, onSeekTo }) {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [pos, setPos] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [audioError, setAudioError] = useState(false);

  useEffect(() => {
    setPos(0);
    setIsPlaying(false);
    setAudioError(false);
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.playbackRate = playbackRate;
    }
  }, [audioUrl]);

  // When parent triggers seek (e.g. turn clicked)
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
      audioRef.current.play()
        .then(() => setIsPlaying(true))
        .catch((e) => {
          console.error("Playback error:", e);
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

  const handleSliderChange = (e) => {
    const val = parseFloat(e.target.value);
    setPos(val);
    if (audioRef.current) {
      audioRef.current.currentTime = val;
    }
    if (onTimeUpdate) {
      onTimeUpdate(val);
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
    if (!secs || isNaN(secs)) return '00:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="glass-panel p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md">
      <audio
        ref={audioRef}
        src={audioUrl}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={() => setIsPlaying(false)}
        onError={() => setAudioError(true)}
        preload="metadata"
      />

      <div className="flex flex-col gap-3">
        {/* Top Controls Row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              disabled={audioError}
              className={`w-10 h-10 rounded-lg flex items-center justify-center font-medium transition-all ${
                isPlaying
                  ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/20'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-100'
              }`}
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
            </button>

            <button
              onClick={() => {
                if (audioRef.current) {
                  audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 5);
                }
              }}
              className="p-2 rounded-lg bg-slate-800/70 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
              title="Rewind 5s"
            >
              <RotateCcw className="w-4 h-4" />
            </button>

            <button
              onClick={cycleSpeed}
              className="px-2.5 py-1 rounded-lg bg-slate-800/70 hover:bg-slate-800 text-xs font-mono text-cyan-400 font-semibold transition-colors"
              title="Change Speed"
            >
              {playbackRate}x
            </button>

            <button
              onClick={toggleMute}
              className="p-2 rounded-lg bg-slate-800/70 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? <VolumeX className="w-4 h-4 text-rose-400" /> : <Volume2 className="w-4 h-4" />}
            </button>
          </div>

          {/* Time display & Channel Indicator */}
          <div className="flex items-center gap-4 text-xs">
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800/50 border border-slate-700/50 text-slate-400 font-mono">
              <Headphones className="w-3.5 h-3.5 text-cyan-400" />
              <span>Ch 1 (Agent) &bull; Ch 2 (Customer)</span>
            </div>

            <div className="font-mono text-slate-300 bg-slate-950/60 px-2.5 py-1 rounded-md border border-slate-800">
              <span className="text-cyan-400">{formatTime(pos)}</span>
              <span className="text-slate-500 mx-1">/</span>
              <span>{formatTime(duration)}</span>
            </div>
          </div>
        </div>

        {/* Seek Bar */}
        <div className="flex items-center gap-2">
          <input
            type="range"
            min={0}
            max={duration || 100}
            step={0.1}
            value={pos}
            onChange={handleSliderChange}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 hover:accent-cyan-300 focus:outline-none"
          />
        </div>

        {audioError && (
          <div className="text-xs text-rose-400 bg-rose-950/30 border border-rose-800/40 rounded px-2.5 py-1.5 flex items-center justify-between">
            <span>Audio stream unavailable or audio file missing for this interaction.</span>
            <span className="font-mono text-[10px] text-slate-400">Endpoint: /audio</span>
          </div>
        )}
      </div>
    </div>
  );
}

