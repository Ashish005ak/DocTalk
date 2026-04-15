import { useState } from 'react';
import type { ClinicalStateView, Confidence, HypothesisEntry, Phase } from '../types';

interface ContextPanelProps {
  state: ClinicalStateView | null;
}

const PHASE_STYLES: Record<Phase, { bg: string; text: string; border: string }> = {
  intake: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  exploring: { bg: 'bg-indigo-500/10', text: 'text-indigo-400', border: 'border-indigo-500/30' },
  narrowing: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30' },
  summary: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
};

const CONFIDENCE_STYLES: Record<Confidence, { bg: string; text: string; width: string }> = {
  low: { bg: 'bg-red-500', text: 'text-red-400', width: 'w-1/3' },
  medium: { bg: 'bg-amber-500', text: 'text-amber-400', width: 'w-2/3' },
  high: { bg: 'bg-emerald-500', text: 'text-emerald-400', width: 'w-full' },
};

function ScoreBar({ score, max = 1.0 }: { score: number; max?: number }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  return (
    <div className="h-1.5 w-full bg-[#1e2330] rounded-full overflow-hidden">
      <div
        className="h-full bg-indigo-500 rounded-full transition-all duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function HypothesisCard({ entry, isLeading }: { entry: HypothesisEntry; isLeading?: boolean }) {
  return (
    <div className={`rounded-lg px-3 py-2 animate-fadeIn ${
      isLeading
        ? 'bg-indigo-500/10 border border-indigo-500/30'
        : 'bg-[#1a1f2e] border border-[#2d3555]'
    }`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`text-xs font-medium ${isLeading ? 'text-indigo-400' : 'text-slate-300'}`}>
          {entry.name}
        </span>
        <span className="text-[10px] text-slate-500">{(entry.score * 100).toFixed(0)}%</span>
      </div>
      <ScoreBar score={entry.score} />
    </div>
  );
}

function CollapsibleSection({
  title,
  count,
  countColor = 'text-indigo-400',
  defaultOpen = true,
  children,
}: {
  title: string;
  count?: number;
  countColor?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 w-full text-left group"
      >
        <svg
          className={`w-3 h-3 text-slate-600 transition-transform ${open ? 'rotate-90' : ''}`}
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4.5 2l5 4-5 4V2z" />
        </svg>
        <h3 className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-slate-400 transition-colors">
          {title}
        </h3>
        {count !== undefined && count > 0 && (
          <span className={`text-[11px] ${countColor} normal-case tracking-normal`}>
            ({count})
          </span>
        )}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

export function ContextPanel({ state }: ContextPanelProps) {
  if (!state || state.turn_count === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-10 h-10 rounded-lg bg-[#1e2330] flex items-center justify-center mb-3">
          <svg className="w-5 h-5 text-slate-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <p className="text-sm text-slate-600">Waiting for conversation...</p>
        <p className="text-xs text-slate-700 mt-1">Clinical context will appear after the first exchange</p>
      </div>
    );
  }

  const phaseStyle = PHASE_STYLES[state.phase] ?? PHASE_STYLES.intake;
  const confStyle = CONFIDENCE_STYLES[state.confidence] ?? CONFIDENCE_STYLES.low;
  const infoEntries = Object.entries(state.information_gathered);
  const isSummary = state.phase === 'summary';

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* Summary complete indicator */}
        {isSummary && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-4 h-4 text-emerald-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="text-sm font-semibold text-emerald-400">Consultation Complete</span>
            </div>
            <p className="text-xs text-emerald-300/70">
              All relevant clinical history has been gathered. A summary has been provided.
            </p>
          </div>
        )}

        {/* Phase + Confidence */}
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-1 rounded-md text-xs font-medium border ${phaseStyle.bg} ${phaseStyle.text} ${phaseStyle.border}`}>
            {state.phase.charAt(0).toUpperCase() + state.phase.slice(1)}
          </span>
          <div className="flex items-center gap-2 flex-1">
            <span className={`text-[10px] font-medium uppercase ${confStyle.text}`}>
              {state.confidence}
            </span>
            <div className="flex-1 h-1.5 bg-[#1e2330] rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all duration-500 ${confStyle.bg} ${confStyle.width}`} />
            </div>
          </div>
        </div>

        {/* Red Flags */}
        {state.confirmed_red_flag_ids.length > 0 && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2.5">
            <div className="flex items-center gap-2 mb-2">
              <svg className="w-4 h-4 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">Red Flags</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {state.confirmed_red_flag_ids.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-red-500/20 text-red-300 border border-red-500/30"
                >
                  {id.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Information Gathered */}
        {infoEntries.length > 0 && (
          <CollapsibleSection title="Information Gathered" count={infoEntries.length}>
            <div className="space-y-1.5">
              {infoEntries.map(([key, value]) => (
                <div
                  key={key}
                  className="bg-[#1a1f2e] border border-[#2d3555] rounded-lg px-3 py-2 animate-fadeIn"
                >
                  <span className="text-xs font-medium text-indigo-400">{key.replace(/_/g, ' ')}:</span>{' '}
                  <span className="text-xs text-slate-300">{value}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* Denied Symptoms */}
        {state.denied_symptoms.length > 0 && (
          <CollapsibleSection
            title="Denied Symptoms"
            count={state.denied_symptoms.length}
            countColor="text-slate-500"
            defaultOpen={false}
          >
            <div className="flex flex-wrap gap-1.5">
              {state.denied_symptoms.map((sym) => (
                <span
                  key={sym}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a1f2e] text-slate-500 border border-[#2d3555] line-through"
                >
                  {sym.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* Hypotheses */}
        {state.hypothesis && (
          <CollapsibleSection title="Hypotheses">
            <div className="space-y-2">
              {state.hypothesis.leading && (
                <HypothesisCard entry={state.hypothesis.leading} isLeading />
              )}
              {state.hypothesis.differential.map((h) => (
                <HypothesisCard key={h.id} entry={h} />
              ))}
              {state.hypothesis.ruled_out.length > 0 && (
                <div className="mt-1">
                  <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Ruled Out</p>
                  <div className="flex flex-wrap gap-1.5">
                    {state.hypothesis.ruled_out.map((h) => (
                      <span
                        key={h.id}
                        className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#1a1f2e] text-slate-600 border border-[#2d3555] line-through"
                      >
                        {h.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CollapsibleSection>
        )}

        {/* Remaining Gaps */}
        {state.remaining_gaps.length > 0 && (
          <CollapsibleSection
            title="Remaining Gaps"
            count={state.remaining_gaps.length}
            countColor="text-orange-400"
          >
            <div className="space-y-1">
              {state.remaining_gaps.map((gap) => (
                <div key={gap} className="flex items-center gap-2 text-xs">
                  <span className="w-4 h-4 rounded border border-orange-500/40 bg-orange-500/10 flex items-center justify-center flex-shrink-0">
                    <span className="text-[10px] text-orange-400">?</span>
                  </span>
                  <span className="text-slate-300">{gap.replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-[#2d3555] bg-[#141927] flex items-center justify-between">
        <span className="text-[11px] text-slate-600">
          Turn {state.turn_count}
          {isSummary && (
            <span className="ml-2 text-emerald-500">&bull; Complete</span>
          )}
        </span>
      </div>
    </div>
  );
}
