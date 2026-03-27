import { useEffect, useState } from 'react';
import type { ContextObject, Signal } from '../types';

interface ContextPanelProps {
  context: ContextObject | null;
  gapCategories: string[];
}

const SIGNAL_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  red_flag: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30' },
  contradiction: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  vague: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  emotional: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
};

function SignalTag({ signal }: { signal: Signal }) {
  const style = SIGNAL_STYLES[signal.type] ?? SIGNAL_STYLES.vague;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border ${style.bg} ${style.text} ${style.border}`}
      title={signal.detail}
    >
      {signal.type.replace(/_/g, ' ')}
    </span>
  );
}

function timeAgo(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  return `${minutes}m ago`;
}

export function ContextPanel({ context, gapCategories }: ContextPanelProps) {
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (context && context.turn_count > 0) {
      setLastUpdate(Date.now());
    }
  }, [context]);

  useEffect(() => {
    if (lastUpdate === null) return;
    const interval = setInterval(() => {
      setElapsed(Date.now() - lastUpdate);
    }, 1000);
    return () => clearInterval(interval);
  }, [lastUpdate]);

  if (!context || context.turn_count === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-10 h-10 rounded-lg bg-[#1e2330] flex items-center justify-center mb-3">
          <svg className="w-5 h-5 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <p className="text-sm text-slate-600">Waiting for conversation...</p>
        <p className="text-xs text-slate-700 mt-1">Context will appear after the first responder turn</p>
      </div>
    );
  }

  const resolvedGaps = gapCategories.filter((g) => !context.gaps.includes(g));

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* Core Topic */}
        {context.core_topic && (
          <div>
            <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">Core Topic</h3>
            <p className="text-sm text-white font-medium">{context.core_topic}</p>
          </div>
        )}

        {/* Information Gathered */}
        {context.information_gathered.length > 0 && (
          <div>
            <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
              Information Gathered
              <span className="ml-1.5 text-indigo-400 normal-case tracking-normal">
                ({context.information_gathered.length})
              </span>
            </h3>
            <div className="space-y-1.5">
              {context.information_gathered.map((item, i) => (
                <div
                  key={`${item.key}-${i}`}
                  className="bg-[#1a1f2e] border border-[#2d3555] rounded-lg px-3 py-2 animate-fadeIn"
                >
                  <span className="text-xs font-medium text-indigo-400">{item.key}:</span>{' '}
                  <span className="text-xs text-slate-300">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Gaps */}
        {(gapCategories.length > 0 || context.gaps.length > 0) && (
          <div>
            <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
              Gaps
              <span className="ml-1.5 text-orange-400 normal-case tracking-normal">
                ({context.gaps.length} remaining)
              </span>
            </h3>
            <div className="space-y-1">
              {context.gaps.map((gap) => (
                <div key={gap} className="flex items-center gap-2 text-xs">
                  <span className="w-4 h-4 rounded border border-orange-500/40 bg-orange-500/10 flex items-center justify-center flex-shrink-0">
                    <span className="text-[10px] text-orange-400">?</span>
                  </span>
                  <span className="text-slate-300">{gap}</span>
                </div>
              ))}
              {resolvedGaps.map((gap) => (
                <div key={gap} className="flex items-center gap-2 text-xs">
                  <span className="w-4 h-4 rounded border border-emerald-500/40 bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
                    <svg className="w-2.5 h-2.5 text-emerald-400" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2}>
                      <path d="M2 6l3 3 5-5" />
                    </svg>
                  </span>
                  <span className="text-slate-600 line-through">{gap}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Signals */}
        {context.signals.length > 0 && (
          <div>
            <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
              Signals
              <span className="ml-1.5 text-red-400 normal-case tracking-normal">
                ({context.signals.length})
              </span>
            </h3>
            <div className="space-y-2">
              {context.signals.map((sig, i) => (
                <div
                  key={`${sig.type}-${i}`}
                  className="bg-[#1a1f2e] border border-[#2d3555] rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <SignalTag signal={sig} />
                  </div>
                  <p className="text-xs text-slate-400">{sig.detail}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-[#2d3555] bg-[#141927] flex items-center justify-between">
        <span className="text-[11px] text-slate-600">
          Turn {context.turn_count}
        </span>
        {lastUpdate !== null && (
          <span className="text-[11px] text-slate-600">
            Updated {timeAgo(elapsed)}
          </span>
        )}
      </div>
    </div>
  );
}
