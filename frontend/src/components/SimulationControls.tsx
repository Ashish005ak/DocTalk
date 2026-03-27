import type { ConnectionState } from '../hooks/useWebSocket';
import type { ReplayState, Speed, WSAction } from '../types';

interface SimulationControlsProps {
  replayState: ReplayState;
  speed: Speed;
  currentTurn: number;
  totalTurns: number;
  transcriptTitle: string;
  connectionState: ConnectionState;
  onAction: (action: WSAction) => void;
  onReset: () => void; // returns to session setup
}

const SPEED_OPTIONS: Speed[] = [0.5, 1.0, 2.0, 4.0];

const CONNECTION_COLORS: Record<ConnectionState, string> = {
  connected: 'bg-green-500',
  connecting: 'bg-yellow-500 animate-pulse',
  disconnected: 'bg-red-500',
  error: 'bg-red-500',
};

const CONNECTION_LABELS: Record<ConnectionState, string> = {
  connected: 'Connected',
  connecting: 'Connecting…',
  disconnected: 'Disconnected',
  error: 'Error',
};

export function SimulationControls({
  replayState,
  speed,
  currentTurn,
  totalTurns,
  transcriptTitle,
  connectionState,
  onAction,
  onReset,
}: SimulationControlsProps) {
  const isPlaying = replayState === 'playing';
  const isFinished = replayState === 'finished';
  const canPlay = replayState === 'idle' || replayState === 'paused' || isFinished;
  const progressPct = totalTurns > 0 ? Math.round((currentTurn / totalTurns) * 100) : 0;

  const handlePlayPause = () => {
    if (isPlaying) {
      onAction({ action: 'pause' });
    } else if (replayState === 'paused') {
      onAction({ action: 'resume' });
    } else {
      onAction({ action: 'start' });
    }
  };

  const handleStop = () => {
    onAction({ action: 'stop' });
  };

  const handleSpeed = (s: Speed) => {
    onAction({ action: 'set_speed', speed: s });
  };

  return (
    <div className="bg-[#1a1f2e] border-b border-[#2d3555] px-4 py-3">
      <div className="flex items-center gap-4">

        {/* Logo / title */}
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-md bg-indigo-600 flex items-center justify-center text-white font-bold text-xs flex-shrink-0">C</div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-white truncate">{transcriptTitle || 'ConvoNudge'}</p>
            <p className="text-xs text-slate-500">
              {isFinished ? 'Finished' : `Turn ${currentTurn} / ${totalTurns}`}
            </p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="flex-1 hidden sm:block">
          <div className="h-1.5 bg-[#252d42] rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>

        {/* Play / Pause */}
        <button
          onClick={handlePlayPause}
          disabled={connectionState !== 'connected'}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          {isPlaying ? (
            <>
              <PauseIcon />
              Pause
            </>
          ) : isFinished ? (
            <>
              <ReplayIcon />
              Replay
            </>
          ) : (
            <>
              <PlayIcon />
              Play
            </>
          )}
        </button>

        {/* Stop */}
        {(isPlaying || replayState === 'paused') && (
          <button
            onClick={handleStop}
            className="px-3 py-1.5 bg-[#252d42] border border-[#3d4a6b] text-slate-300 hover:bg-[#2d3a56] rounded-lg text-sm transition-colors"
          >
            Stop
          </button>
        )}

        {/* Speed controls */}
        <div className="flex items-center gap-1 bg-[#252d42] border border-[#3d4a6b] rounded-lg p-0.5">
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => handleSpeed(s)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                speed === s
                  ? 'bg-indigo-600 text-white'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {s === 0.5 ? '0.5×' : `${s}×`}
            </button>
          ))}
        </div>

        {/* New session */}
        <button
          onClick={onReset}
          className="px-3 py-1.5 text-slate-400 hover:text-white text-sm transition-colors"
          title="New session"
        >
          ⊞ New
        </button>

        {/* Connection indicator */}
        <div className="flex items-center gap-1.5 ml-auto">
          <div className={`w-2 h-2 rounded-full ${CONNECTION_COLORS[connectionState]}`} />
          <span className="text-xs text-slate-500 hidden md:block">{CONNECTION_LABELS[connectionState]}</span>
        </div>
      </div>
    </div>
  );
}

function PlayIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
    </svg>
  );
}

function ReplayIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" />
    </svg>
  );
}
